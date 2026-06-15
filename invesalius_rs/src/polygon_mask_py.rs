use numpy::{PyArray2, PyReadonlyArray2};
use pyo3::prelude::*;

use crate::polygon_mask::polygon2mask_internal;

#[pyfunction]
pub fn polygon2mask_rs<'py>(
    py: Python<'py>,
    shape: (usize, usize),
    polygon: PyReadonlyArray2<f64>,
) -> PyResult<Bound<'py, PyArray2<bool>>> {
    // Convert the zero-copy numpy array into a Rust friendly structure
    let poly_array = polygon.as_array();
    
    // We expect an Nx2 array of points (x, y)
    let points: Vec<[f64; 2]> = poly_array
        .rows()
        .into_iter()
        .map(|r| [r[0], r[1]])
        .collect();
    
    // Call the internal mathematical logic
    let mask = polygon2mask_internal(shape, &points);
    
    // Convert the processed rust matrix back into a numpy array bound to the Python context
    Ok(PyArray2::from_array(py, &mask))
}
