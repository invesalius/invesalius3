use ndarray::Array2;
use numpy::ToPyArray;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

use crate::marching_tetrahedra::marching_tetrahedra_mask;
use crate::types::MaskTypes3;

#[pyfunction]
pub fn marching_tetrahedra<'py>(
    py: Python<'py>,
    mask: MaskTypes3<'py>,
    spacing: [f64; 3],
) -> PyResult<(Py<PyAny>, Py<PyAny>)> {
    let mesh = match mask {
        MaskTypes3::U8(mask) => marching_tetrahedra_mask(mask.as_array(), spacing),
    };

    let mut vertices_flat = Vec::with_capacity(mesh.vertices.len() * 3);
    for vertex in &mesh.vertices {
        vertices_flat.extend_from_slice(vertex);
    }

    let mut faces_flat = Vec::with_capacity(mesh.faces.len() * 3);
    for face in &mesh.faces {
        faces_flat.extend_from_slice(face);
    }

    let vertices = Array2::from_shape_vec((mesh.vertices.len(), 3), vertices_flat)
        .map_err(|error| PyValueError::new_err(error.to_string()))?;
    let faces = Array2::from_shape_vec((mesh.faces.len(), 3), faces_flat)
        .map_err(|error| PyValueError::new_err(error.to_string()))?;

    Ok((
        vertices.to_pyarray(py).into(),
        faces.to_pyarray(py).into(),
    ))
}
