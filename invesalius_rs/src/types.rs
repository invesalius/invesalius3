use numpy::{PyReadonlyArray2, PyReadonlyArray3, PyReadwriteArray2, PyReadwriteArray3};
use pyo3::FromPyObject;

// --- 3D read-only ---
#[derive(FromPyObject)]
pub enum ImageTypes3<'py> {
    F64(PyReadonlyArray3<'py, f64>),
    I16(PyReadonlyArray3<'py, i16>),
    U8(PyReadonlyArray3<'py, u8>),
}

#[derive(FromPyObject)]
pub enum MaskTypes3<'py> {
    U8(PyReadonlyArray3<'py, u8>),
}

// --- 3D read-write ---
#[derive(FromPyObject)]
pub enum ImageTypesMut3<'py> {
    F64(PyReadwriteArray3<'py, f64>),
    I16(PyReadwriteArray3<'py, i16>),
    U8(PyReadwriteArray3<'py, u8>),
}

#[derive(FromPyObject)]
pub enum MaskTypesMut3<'py> {
    U8(PyReadwriteArray3<'py, u8>),
}

#[derive(FromPyObject)]
pub enum LabelsTypes3<'py> {
    I16(PyReadonlyArray3<'py, i16>),
    I32(PyReadonlyArray3<'py, i32>),
    I64(PyReadonlyArray3<'py, i64>),
}

// --- 2D read-only ---
#[derive(FromPyObject)]
pub enum MaskTypes2<'py> {
    U8(PyReadonlyArray2<'py, u8>),
}

// --- 2D read-write ---
#[derive(FromPyObject)]
pub enum ImageTypesMut2<'py> {
    F64(PyReadwriteArray2<'py, f64>),
    I16(PyReadwriteArray2<'py, i16>),
    U8(PyReadwriteArray2<'py, u8>),
}

#[derive(FromPyObject)]
pub enum MaskTypesMut2<'py> {
    I16(PyReadwriteArray2<'py, i16>),
    U8(PyReadwriteArray2<'py, u8>),
}

// --- Mesh (2D read-write) ---
#[derive(FromPyObject)]
pub enum VertexArray<'py> {
    F64(PyReadwriteArray2<'py, f64>),
    F32(PyReadwriteArray2<'py, f32>),
}

#[derive(FromPyObject)]
pub enum FaceArray<'py> {
    I64(PyReadwriteArray2<'py, i64>),
    U64(PyReadwriteArray2<'py, u64>),
    I32(PyReadwriteArray2<'py, i32>),
    U32(PyReadwriteArray2<'py, u32>),
}
