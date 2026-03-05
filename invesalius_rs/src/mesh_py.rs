use pyo3::prelude::*;

use crate::mesh::context_aware_smoothing_internal;
use crate::types::{FaceArray, VertexArray};

#[pyfunction]
pub fn context_aware_smoothing<'py>(
    vertices: VertexArray<'py>,
    faces: FaceArray<'py>,
    normals: VertexArray<'py>,
    t: f64,
    tmax: f64,
    bmin: f64,
    n_iters: u32,
) -> PyResult<()> {
    match (vertices, faces, normals) {
        (
            VertexArray::F32(mut vertices),
            FaceArray::I64(mut faces),
            VertexArray::F32(mut normals),
        ) => {
            println!("F32 vertices, I64 faces");
            context_aware_smoothing_internal(
                vertices.as_array_mut(),
                faces.as_array_mut(),
                normals.as_array_mut(),
                t,
                tmax,
                bmin,
                n_iters,
            );
            Ok(())
        }
        (
            VertexArray::F32(mut vertices),
            FaceArray::I64(mut faces),
            VertexArray::F64(mut normals),
        ) => {
            println!("F32 vertices, I64 faces");
            context_aware_smoothing_internal(
                vertices.as_array_mut(),
                faces.as_array_mut(),
                normals.as_array_mut(),
                t,
                tmax,
                bmin,
                n_iters,
            );
            Ok(())
        }
        (
            VertexArray::F32(mut vertices),
            FaceArray::U64(mut faces),
            VertexArray::F32(mut normals),
        ) => {
            println!("F32 vertices, U64 faces");
            context_aware_smoothing_internal(
                vertices.as_array_mut(),
                faces.as_array_mut(),
                normals.as_array_mut(),
                t,
                tmax,
                bmin,
                n_iters,
            );
            Ok(())
        }
        (
            VertexArray::F32(mut vertices),
            FaceArray::U64(mut faces),
            VertexArray::F64(mut normals),
        ) => {
            println!("F32 vertices, U64 faces");
            context_aware_smoothing_internal(
                vertices.as_array_mut(),
                faces.as_array_mut(),
                normals.as_array_mut(),
                t,
                tmax,
                bmin,
                n_iters,
            );
            Ok(())
        }
        (
            VertexArray::F32(mut vertices),
            FaceArray::I32(mut faces),
            VertexArray::F32(mut normals),
        ) => {
            println!("F32 vertices, I32 faces");
            context_aware_smoothing_internal(
                vertices.as_array_mut(),
                faces.as_array_mut(),
                normals.as_array_mut(),
                t,
                tmax,
                bmin,
                n_iters,
            );
            Ok(())
        }
        (
            VertexArray::F32(mut vertices),
            FaceArray::I32(mut faces),
            VertexArray::F64(mut normals),
        ) => {
            println!("F32 vertices, I32 faces");
            context_aware_smoothing_internal(
                vertices.as_array_mut(),
                faces.as_array_mut(),
                normals.as_array_mut(),
                t,
                tmax,
                bmin,
                n_iters,
            );
            Ok(())
        }
        (
            VertexArray::F32(mut vertices),
            FaceArray::U32(mut faces),
            VertexArray::F32(mut normals),
        ) => {
            println!("F32 vertices, U32 faces");
            context_aware_smoothing_internal(
                vertices.as_array_mut(),
                faces.as_array_mut(),
                normals.as_array_mut(),
                t,
                tmax,
                bmin,
                n_iters,
            );
            Ok(())
        }
        (
            VertexArray::F32(mut vertices),
            FaceArray::U32(mut faces),
            VertexArray::F64(mut normals),
        ) => {
            println!("F32 vertices, U32 faces");
            context_aware_smoothing_internal(
                vertices.as_array_mut(),
                faces.as_array_mut(),
                normals.as_array_mut(),
                t,
                tmax,
                bmin,
                n_iters,
            );
            Ok(())
        }
        (
            VertexArray::F64(mut vertices),
            FaceArray::I64(mut faces),
            VertexArray::F32(mut normals),
        ) => {
            println!("F64 vertices, I64 faces");
            context_aware_smoothing_internal(
                vertices.as_array_mut(),
                faces.as_array_mut(),
                normals.as_array_mut(),
                t,
                tmax,
                bmin,
                n_iters,
            );
            Ok(())
        }
        (
            VertexArray::F64(mut vertices),
            FaceArray::I64(mut faces),
            VertexArray::F64(mut normals),
        ) => {
            println!("F64 vertices, I64 faces");
            context_aware_smoothing_internal(
                vertices.as_array_mut(),
                faces.as_array_mut(),
                normals.as_array_mut(),
                t,
                tmax,
                bmin,
                n_iters,
            );
            Ok(())
        }
        (
            VertexArray::F64(mut vertices),
            FaceArray::U64(mut faces),
            VertexArray::F32(mut normals),
        ) => {
            println!("F64 vertices, U64 faces");
            context_aware_smoothing_internal(
                vertices.as_array_mut(),
                faces.as_array_mut(),
                normals.as_array_mut(),
                t,
                tmax,
                bmin,
                n_iters,
            );
            Ok(())
        }
        (
            VertexArray::F64(mut vertices),
            FaceArray::U64(mut faces),
            VertexArray::F64(mut normals),
        ) => {
            println!("F64 vertices, U64 faces");
            context_aware_smoothing_internal(
                vertices.as_array_mut(),
                faces.as_array_mut(),
                normals.as_array_mut(),
                t,
                tmax,
                bmin,
                n_iters,
            );
            Ok(())
        }
        (
            VertexArray::F64(mut vertices),
            FaceArray::I32(mut faces),
            VertexArray::F32(mut normals),
        ) => {
            println!("F64 vertices, I32 faces");
            context_aware_smoothing_internal(
                vertices.as_array_mut(),
                faces.as_array_mut(),
                normals.as_array_mut(),
                t,
                tmax,
                bmin,
                n_iters,
            );
            Ok(())
        }
        (
            VertexArray::F64(mut vertices),
            FaceArray::I32(mut faces),
            VertexArray::F64(mut normals),
        ) => {
            println!("F64 vertices, I32 faces");
            context_aware_smoothing_internal(
                vertices.as_array_mut(),
                faces.as_array_mut(),
                normals.as_array_mut(),
                t,
                tmax,
                bmin,
                n_iters,
            );
            Ok(())
        }
        (
            VertexArray::F64(mut vertices),
            FaceArray::U32(mut faces),
            VertexArray::F32(mut normals),
        ) => {
            println!("F64 vertices, U32 faces");
            context_aware_smoothing_internal(
                vertices.as_array_mut(),
                faces.as_array_mut(),
                normals.as_array_mut(),
                t,
                tmax,
                bmin,
                n_iters,
            );
            Ok(())
        }
        (
            VertexArray::F64(mut vertices),
            FaceArray::U32(mut faces),
            VertexArray::F64(mut normals),
        ) => {
            println!("F64 vertices, U32 faces");
            context_aware_smoothing_internal(
                vertices.as_array_mut(),
                faces.as_array_mut(),
                normals.as_array_mut(),
                t,
                tmax,
                bmin,
                n_iters,
            );
            Ok(())
        }
    }
}
