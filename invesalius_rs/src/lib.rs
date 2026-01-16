use pyo3::prelude::*;

mod types;
mod interpolation;
mod floodfill;
mod mips;
mod transforms;
mod mask_cut;
mod mesh;

/// InVesalius Rust extension module
#[pymodule]
fn _native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    // Interpolation functions
    m.add_function(wrap_pyfunction!(interpolation::trilin_interpolate_py, m)?)?;
    m.add_function(wrap_pyfunction!(interpolation::nearest_neighbour_interp, m)?)?;
    m.add_function(wrap_pyfunction!(interpolation::tricub_interpolate_py, m)?)?;
    m.add_function(wrap_pyfunction!(interpolation::tricub_interpolate2_py, m)?)?;
    m.add_function(wrap_pyfunction!(interpolation::lanczos_interpolate_py, m)?)?;
    
    // Floodfill functions
    m.add_function(wrap_pyfunction!(floodfill::floodfill, m)?)?;
    m.add_function(wrap_pyfunction!(floodfill::floodfill_threshold, m)?)?;
    m.add_function(wrap_pyfunction!(floodfill::floodfill_auto_threshold, m)?)?;
    m.add_function(wrap_pyfunction!(floodfill::fill_holes_automatically, m)?)?;
    
    // MIPS functions
    m.add_function(wrap_pyfunction!(mips::lmip, m)?)?;
    m.add_function(wrap_pyfunction!(mips::mida, m)?)?;
    m.add_function(wrap_pyfunction!(mips::mida_old, m)?)?;
    m.add_function(wrap_pyfunction!(mips::fast_countour_mip, m)?)?;
    
    // Transform functions
    m.add_function(wrap_pyfunction!(transforms::apply_view_matrix_transform, m)?)?;
    m.add_function(wrap_pyfunction!(transforms::convolve_non_zero, m)?)?;
    
    // Mask cut function
    m.add_function(wrap_pyfunction!(mask_cut::mask_cut, m)?)?;
    
    // Mesh class
    m.add_class::<mesh::Mesh>()?;
    
    Ok(())
}
