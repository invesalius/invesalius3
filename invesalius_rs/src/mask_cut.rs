use nalgebra::{Matrix4, Vector4};
use numpy::{PyReadonlyArray1, PyReadonlyArray2, PyReadonlyArray3, PyReadwriteArray3};
use pyo3::prelude::*;

#[pyfunction]
pub fn mask_cut(
    _image: PyReadonlyArray3<i16>,
    x_coords: PyReadonlyArray1<i32>,
    y_coords: PyReadonlyArray1<i32>,
    z_coords: PyReadonlyArray1<i32>,
    sx: f32,
    sy: f32,
    sz: f32,
    max_depth: f32,
    mask: PyReadonlyArray2<u8>,
    m: PyReadonlyArray2<f64>,
    mv: PyReadonlyArray2<f64>,
    mut out: PyReadwriteArray3<i16>,
) -> PyResult<()> {
    let m_slice = m.as_slice().unwrap();
    let mv_slice = mv.as_slice().unwrap();
    let m_nalgebra = Matrix4::from_row_slice(m_slice);
    let mv_nalgebra = Matrix4::from_row_slice(mv_slice);

    let mask_arr = mask.as_array();
    let mask_dims = mask_arr.shape();
    let (h, w) = (mask_dims[0], mask_dims[1]);

    let mut out_arr = out.as_array_mut();

    let x_coords_arr = x_coords.as_array();
    let y_coords_arr = y_coords.as_array();
    let z_coords_arr = z_coords.as_array();

    let n = z_coords_arr.len();

    for i in 0..n {
        let x = x_coords_arr[i] as f64;
        let y = y_coords_arr[i] as f64;
        let z = z_coords_arr[i] as f64;

        let p = Vector4::new(x * sx as f64, y * sy as f64, z * sz as f64, 1.0);

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
                    if mask_arr[[py as usize, px as usize]] != 0 {
                        out_arr[[z as usize, y as usize, x as usize]] = 0;
                    }
                }
            }
        }
    }

    Ok(())
}
