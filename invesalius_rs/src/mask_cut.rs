use nalgebra::{Matrix4, Vector4};
use numpy::{PyReadonlyArray1, PyReadonlyArray2, PyReadonlyArray3, PyReadwriteArray3};
use pyo3::prelude::*;
use ndarray::parallel::prelude::*;

#[pyfunction]
pub fn mask_cut(
    _image: PyReadonlyArray3<u8>,
    x_coords: PyReadonlyArray1<i32>,
    y_coords: PyReadonlyArray1<i32>,
    z_coords: PyReadonlyArray1<i32>,
    sx: f64,
    sy: f64,
    sz: f64,
    max_depth: f64,
    mask: PyReadonlyArray2<bool>,
    m: PyReadonlyArray2<f64>,
    mv: PyReadonlyArray2<f64>,
    mut out: PyReadwriteArray3<u8>,
) -> PyResult<()> {
    let m_slice = m.as_slice().unwrap();
    let mv_slice = mv.as_slice().unwrap();
    let m_nalgebra = Matrix4::from_row_slice(m_slice);
    let mv_nalgebra = Matrix4::from_row_slice(mv_slice);

    let mask_arr = mask.as_array();
    let mask_dims = mask_arr.shape();
    let (h, w) = (mask_dims[0], mask_dims[1]);

    let mut out_arr = out.as_array_mut();
    let out_ptr = out_arr.as_mut_ptr() as usize;
    let out_strides = out_arr.strides();
    let out_shape = out_arr.shape();

    let x_coords_arr = x_coords.as_array();
    let y_coords_arr = y_coords.as_array();
    let z_coords_arr = z_coords.as_array();

    par_azip!((x in x_coords_arr, y in y_coords_arr, z in z_coords_arr) {
        let p = Vector4::new(*x as f64 * sx, *y as f64 * sy, *z as f64 * sz, 1.0);

        let q_ = m_nalgebra * p;
        if q_[3] > 0.0 {
            let q = q_ / q_[3];

            let c_ = mv_nalgebra * p;
            let c = c_ / c_[3];

            let dist = (c[0] * c[0] + c[1] * c[1] + c[2] * c[2]).sqrt();

            if dist <= max_depth as f64 {
                let px = (q[0] / 2.0 + 0.5) * (w - 1) as f64;
                let py = (q[1] / 2.0 + 0.5) * (h - 1) as f64;

                if px >= 0.0 && px < w as f64 && py >= 0.0 && py < h as f64 {
                    if !mask_arr[[py as usize, px as usize]] {
                        let z_idx = *z as usize;
                        let y_idx = *y as usize;
                        let x_idx = *x as usize;
                        
                        if z_idx < out_shape[0] && y_idx < out_shape[1] && x_idx < out_shape[2] {
                            unsafe {
                                let ptr = out_ptr as *mut u8;
                                let offset = z_idx as isize * out_strides[0] 
                                           + y_idx as isize * out_strides[1] 
                                           + x_idx as isize * out_strides[2];
                                *ptr.offset(offset) = 0;
                            }
                        }
                    }
                }
            }
        }
    });

    Ok(())
}
