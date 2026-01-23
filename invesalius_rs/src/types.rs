use numpy::PyArray3;
use pyo3::prelude::*;
use pyo3::FromPyObject;

#[derive(FromPyObject)]
pub enum SupportedArray<'py> {
    F64(Bound<'py, PyArray3<f64>>),
    I16(Bound<'py, PyArray3<i16>>),
    U8(Bound<'py, PyArray3<u8>>),
}
