use pyo3::prelude::*;
use pyo3::exceptions::PyTypeError;

use crate::brush_mask::brush_mask_internal;
use crate::types::{MaskTypesMut3, MaskTypes3};

#[pyfunction]
pub fn brush_mask_rs<'py>(
    _py: Python<'py>,
    out: MaskTypesMut3<'py>,
    orig: Option<MaskTypes3<'py>>,
    spacing: (f64, f64, f64),
    center: (f64, f64, f64),
    radius: f64,
    edit_mode: i32,
) -> PyResult<()> {
    match out {
        MaskTypesMut3::U8(mut out_array) => {
            let orig_array = match &orig {
                Some(MaskTypes3::U8(o)) => Some(o.as_array()),
                None => None,
            };
            brush_mask_internal(out_array.as_array_mut(), orig_array, spacing, center, radius, edit_mode);
            Ok(())
        }
        _ => Err(PyTypeError::new_err("Invalid mask type for brush mask")),
    }
}
