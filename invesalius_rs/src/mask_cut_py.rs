use numpy::PyReadonlyArray2;
use pyo3::exceptions::PyTypeError;
use pyo3::prelude::*;

use crate::mask_cut::mask_cut_internal;
use crate::types::{ImageTypes3, MaskTypesMut3};

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
