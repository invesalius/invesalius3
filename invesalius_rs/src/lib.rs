use pyo3::prelude::*;

mod count_regions;
mod count_regions_py;
mod floodfill;
mod floodfill_py;
mod interpolation;
mod mask_cut;
mod mask_cut_py;
mod mesh;
mod mesh_py;
mod mips;
mod mips_py;
mod texture;
mod texture_py;
mod transforms;
mod transforms_py;
mod types;

/// InVesalius Rust extension module
#[pymodule]
fn _native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    // Floodfill functions
    m.add_function(wrap_pyfunction!(floodfill_py::floodfill, m)?)?;
    m.add_function(wrap_pyfunction!(floodfill_py::floodfill_threshold, m)?)?;
    m.add_function(wrap_pyfunction!(
        floodfill_py::floodfill_threshold_inplace,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(floodfill_py::floodfill_auto_threshold, m)?)?;
    m.add_function(wrap_pyfunction!(floodfill_py::fill_holes_automatically, m)?)?;
    m.add_function(wrap_pyfunction!(floodfill_py::jump_flooding, m)?)?;

    // Floodfill voronoi function
    m.add_function(wrap_pyfunction!(
        floodfill_py::floodfill_voronoi_inplace,
        m
    )?)?;

    // MIPS functions
    m.add_function(wrap_pyfunction!(mips_py::mida, m)?)?;
    m.add_function(wrap_pyfunction!(mips_py::mida_old, m)?)?;
    m.add_function(wrap_pyfunction!(mips_py::fast_countour_mip, m)?)?;

    // Transform functions
    m.add_function(wrap_pyfunction!(
        transforms_py::apply_view_matrix_transform,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(transforms_py::convolve_non_zero, m)?)?;

    // Mask cut function
    m.add_function(wrap_pyfunction!(mask_cut_py::mask_cut, m)?)?;

    // context aware smoothing function
    m.add_function(wrap_pyfunction!(mesh_py::context_aware_smoothing, m)?)?;

    // Count regions function
    m.add_function(wrap_pyfunction!(count_regions_py::count_regions, m)?)?;

    // Texture generation functions
    m.add_function(wrap_pyfunction!(texture_py::generate_surface_texture, m)?)?;
    m.add_function(wrap_pyfunction!(texture_py::generate_tcoords, m)?)?;
    m.add_function(wrap_pyfunction!(texture_py::generate_tcoords_hf, m)?)?;

    Ok(())
}
