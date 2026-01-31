use pyo3::prelude::*;

mod floodfill;
mod interpolation;
mod mask_cut;
mod mesh;
mod mips;
mod transforms;
mod types;

/// InVesalius Rust extension module
#[pymodule]
fn _native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    // Interpolation functions
    m.add_function(wrap_pyfunction!(interpolation::trilin_interpolate_py, m)?)?;
    m.add_function(wrap_pyfunction!(
        interpolation::nearest_neighbour_interp,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(interpolation::tricub_interpolate_py, m)?)?;
    m.add_function(wrap_pyfunction!(interpolation::tricub_interpolate2_py, m)?)?;
    m.add_function(wrap_pyfunction!(interpolation::lanczos_interpolate_py, m)?)?;

    // Floodfill functions
    m.add_function(wrap_pyfunction!(floodfill::floodfill, m)?)?;
    m.add_function(wrap_pyfunction!(floodfill::floodfill_threshold, m)?)?;
    m.add_function(wrap_pyfunction!(floodfill::floodfill_threshold_inplace, m)?)?;
    m.add_function(wrap_pyfunction!(floodfill::floodfill_auto_threshold, m)?)?;
    m.add_function(wrap_pyfunction!(floodfill::fill_holes_automatically, m)?)?;

    // MIPS functions
    m.add_function(wrap_pyfunction!(mips::mida, m)?)?;
    m.add_function(wrap_pyfunction!(mips::mida_old, m)?)?;
    m.add_function(wrap_pyfunction!(mips::fast_countour_mip, m)?)?;

    // Transform functions
    m.add_function(wrap_pyfunction!(
        transforms::apply_view_matrix_transform,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(transforms::convolve_non_zero, m)?)?;

    // Mask cut function
    m.add_function(wrap_pyfunction!(mask_cut::mask_cut, m)?)?;

    // Mesh class (MeshPy usa Mesh<f32, i64, f32>; exposta como "Mesh" no Python)
    m.add_function(wrap_pyfunction!(mesh::context_aware_smoothing, m)?)?;

    Ok(())
}
