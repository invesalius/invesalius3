use numpy::{PyArray2, PyArray3};
use pyo3::prelude::*;
use pyo3::FromPyObject;

pub type MaskT = u8;
pub type VertexT = f32;
pub type NormalT = f32;
pub type VertexIdT = i64;

#[derive(FromPyObject)]
pub enum SupportedArray<'py> {
    F64(Bound<'py, PyArray3<f64>>),
    I16(Bound<'py, PyArray3<i16>>),
    U8(Bound<'py, PyArray3<u8>>),
}

#[derive(FromPyObject)]
pub enum VertexTypes<'py> {
    F32(Bound<'py, PyArray2<f32>>),
    F64(Bound<'py, PyArray2<f64>>),
}

#[derive(FromPyObject)]
pub enum NormalTypes<'py> {
    F32(Bound<'py, PyArray2<f32>>),
    F64(Bound<'py, PyArray2<f64>>),
}

#[derive(FromPyObject)]
pub enum VertexIdTypes<'py> {
    I64(Bound<'py, PyArray2<i64>>),
    U32(Bound<'py, PyArray2<u32>>),
}
