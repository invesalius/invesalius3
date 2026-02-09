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

    // context aware smoothing function
    m.add_function(wrap_pyfunction!(mesh::context_aware_smoothing, m)?)?;

    Ok(())
}
