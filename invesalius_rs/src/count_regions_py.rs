use crate::count_regions::count_regions_internal;
use crate::types::{ImageTypes3, LabelsTypes3};
use ndarray::Array3;
use numpy::{PyReadonlyArray3, PyReadwriteArray3, PyArrayMethods};
use pyo3::exceptions::PyTypeError;
use pyo3::prelude::*;

#[pyfunction]
pub fn count_regions<'py>(
    image: LabelsTypes3<'py>,
    number_regions: usize,
    mut out: PyReadwriteArray3<u32>,
) -> PyResult<()> {
    match image {
        LabelsTypes3::I16(image) => {
            count_regions_internal(image.as_array(), number_regions, out.as_array_mut());
        }
        LabelsTypes3::I32(image) => {
            count_regions_internal(image.as_array(), number_regions, out.as_array_mut());
        }
        LabelsTypes3::I64(image) => {
            count_regions_internal(image.as_array(), number_regions, out.as_array_mut());
        }
    }
    Ok(())
}
