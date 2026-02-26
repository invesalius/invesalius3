use crate::types::{ImageTypes3, MaskTypesMut3};
use nalgebra::{Matrix4, Vector4};
use ndarray::parallel::prelude::*;
use ndarray::{ArrayView2, ArrayView3, ArrayViewMut3};
use num_traits::AsPrimitive;
use num_traits::NumCast;
use numpy::PyReadonlyArray2;
use pyo3::exceptions::PyTypeError;
use pyo3::prelude::*;

pub fn mask_cut_internal<T, U>(
    _image: ArrayView3<T>,
    sx: f64,
    sy: f64,
    sz: f64,
    max_depth: f64,
    mask: ArrayView2<bool>,
    m: ArrayView2<f64>,
    mv: ArrayView2<f64>,
    mut out: ArrayViewMut3<U>,
) where
    T: PartialOrd + Copy + Send + Sync + NumCast + AsPrimitive<f64>,
    U: PartialOrd + Copy + Send + Sync + NumCast + AsPrimitive<i32>,
{
    let m_slice = m.as_slice().unwrap();
    let mv_slice = mv.as_slice().unwrap();
    let m_nalgebra = Matrix4::from_row_slice(m_slice);
    let mv_nalgebra = Matrix4::from_row_slice(mv_slice);

    let mask_dims = mask.shape();
    let (h, w) = (mask_dims[0], mask_dims[1]);

    par_azip!((index (z, y, x), val in &mut out) {
        if val.as_() > 127 {
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
                        && mask[[py as usize, px as usize]] {
                            *val = NumCast::from(0).unwrap();
                        }
                }
            }
        }
    });
}

#[pyfunction]
pub fn mask_cut<'py>(
    image: ImageTypes3<'py>,
    sx: f64,
    sy: f64,
    sz: f64,
    max_depth: f64,
    mask: PyReadonlyArray2<bool>,
    m: PyReadonlyArray2<f64>,
    mv: PyReadonlyArray2<f64>,
    out: MaskTypesMut3<'py>,
) -> PyResult<()> {
    match (image, out) {
        (ImageTypes3::I16(image), MaskTypesMut3::U8(mut out)) => {
            mask_cut_internal(
                image.as_array(),
                sx,
                sy,
                sz,
                max_depth,
                mask.as_array(),
                m.as_array(),
                mv.as_array(),
                out.as_array_mut(),
            );
            Ok(())
        }
        (ImageTypes3::U8(image), MaskTypesMut3::U8(mut out)) => {
            mask_cut_internal(
                image.as_array(),
                sx,
                sy,
                sz,
                max_depth,
                mask.as_array(),
                m.as_array(),
                mv.as_array(),
                out.as_array_mut(),
            );
            Ok(())
        }
        (ImageTypes3::F64(image), MaskTypesMut3::U8(mut out)) => {
            mask_cut_internal(
                image.as_array(),
                sx,
                sy,
                sz,
                max_depth,
                mask.as_array(),
                m.as_array(),
                mv.as_array(),
                out.as_array_mut(),
            );
            Ok(())
        }
        _ => Err(PyTypeError::new_err("Invalid image or mask type")),
    }
}
