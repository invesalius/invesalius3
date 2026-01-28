use nalgebra::{Matrix4, Vector4};
use numpy::{PyReadonlyArray2, PyReadonlyArray3, PyReadwriteArray3};
use pyo3::prelude::*;
use ndarray::parallel::prelude::*;

#[pyfunction]
pub fn mask_cut(
    _image: PyReadonlyArray3<u8>,
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

    par_azip!((index (z, y, x), val in &mut out_arr) {
        if *val > 127 {
            let p = Vector4::new(x as f64 * sx, y as f64 * sy, z as f64 * sz, 1.0);

            let q_ = m_nalgebra * p;
            if q_[3] > 0.0 {
                let q = q_ / q_[3];

                let c_ = mv_nalgebra * p;
                let c = c_ / c_[3];

                let dist = (c[0] * c[0] + c[1] * c[1] + c[2] * c[2]).sqrt();

                if dist <= max_depth {
                    let px = (q[0] / 2.0 + 0.5) * (w - 1) as f64;
                    let py = (q[1] / 2.0 + 0.5) * (h - 1) as f64;

                    if px >= 0.0 && px < w as f64 && py >= 0.0 && py < h as f64
                        && mask_arr[[py as usize, px as usize]] {
                            *val = 0;
                        }
                }
            }
        }
    });

    Ok(())
}
