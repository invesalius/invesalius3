// Surface texture generation for medical imaging
// Ported from Cython to Rust for InVesalius3 integration

use ndarray::prelude::*;
use ndarray::ArrayView3;
use num_traits::NumCast;

// Re-use interpolation from the existing module
use crate::interpolation::trilinear_interpolate_internal;

/// Calculate barycentric coordinates for UV mapping
#[inline]
fn uv_to_barycentric(
    x1: f64,
    y1: f64,
    x2: f64,
    y2: f64,
    x3: f64,
    y3: f64,
    x: f64,
    y: f64,
) -> [f64; 3] {
    let denom = (y2 - y3) * (x1 - x3) + (x3 - x2) * (y1 - y3);
    if denom.abs() < 1e-10 {
        return [1.0, 0.0, 0.0];
    }

    let bar0 = ((y2 - y3) * (x - x3) + (x3 - x2) * (y - y3)) / denom;
    let bar1 = ((y3 - y1) * (x - x3) + (x1 - x3) * (y - y3)) / denom;
    let bar2 = 1.0 - bar0 - bar1;

    [bar0, bar1, bar2]
}

/// Linearly interpolate the VR opacity transfer function curve.
/// `opacity_curve` is an Nx2 array where column 0 = HU value, column 1 = opacity (0..1).
/// The rows must be sorted by HU (ascending).
#[inline]
fn lookup_opacity(hu: f64, opacity_curve: &ArrayView2<f64>) -> f64 {
    let n = opacity_curve.shape()[0];
    if n == 0 {
        return 0.0;
    }
    // Clamp to curve bounds
    if hu <= opacity_curve[[0, 0]] {
        return opacity_curve[[0, 1]];
    }
    if hu >= opacity_curve[[n - 1, 0]] {
        return opacity_curve[[n - 1, 1]];
    }
    // Linear interpolation between surrounding points
    for i in 1..n {
        if hu <= opacity_curve[[i, 0]] {
            let x0 = opacity_curve[[i - 1, 0]];
            let x1 = opacity_curve[[i, 0]];
            let y0 = opacity_curve[[i - 1, 1]];
            let y1 = opacity_curve[[i, 1]];
            let dx = x1 - x0;
            if dx.abs() < 1e-10 {
                return y1;
            }
            let t = (hu - x0) / dx;
            return y0 + t * (y1 - y0);
        }
    }
    opacity_curve[[n - 1, 1]]
}

/// Generate texture coordinates and texture image from mesh and volume data
pub fn generate_surface_texture_internal<V, F, T>(
    vertices: ArrayView2<V>,
    normals: ArrayView2<V>,
    faces: ArrayView2<F>,
    volume: ArrayView3<T>,
    spacing: &[f64; 3],
    window_width: i32,
    window_level: i32,
    clut: ArrayView2<u8>,
    opacity_curve: ArrayView2<f64>,
    texture_dim: usize,
) -> (Array2<f64>, Array3<u8>, Array3<u8>)
where
    V: Copy + Into<f64> + Send + Sync,
    F: Copy + TryInto<usize> + Send + Sync,
    T: Copy + Into<f64> + Send + Sync + NumCast,
{
    let n_faces = faces.shape()[0];

    // Calculate grid dimensions for texture atlas
    let nx = (n_faces as f64).sqrt() as usize;
    let ny = (n_faces as f64 / nx as f64).ceil() as usize;

    let d = texture_dim;
    let dtx = d as f64 / nx as f64;
    let dty = d as f64 / ny as f64;

    // Output arrays
    let mut tcoords = Array2::<f64>::zeros((n_faces, 6));
    let mut texture_image = Array3::<u8>::zeros((d, d, 3));
    let mut texture_normals = Array3::<u8>::zeros((d, d, 3));

    let offset = 2;

    // Apply window/level parameters
    let wl = window_level as f64;
    let ww = window_width as f64;
    let min_val = wl - 0.5 - (ww - 1.0) / 2.0;
    let max_val = wl - 0.5 + (ww - 1.0) / 2.0;

    // Process each triangle
    for tc in 0..n_faces {
        let i = tc % nx;
        let j = tc / nx;

        // Calculate UV coordinates for the triangle corners
        let c0x = (i as f64 * dtx + offset as f64) as usize;
        let c0y = (j as f64 * dty + offset as f64) as usize;
        let c1x = (c0x as f64 + dtx - offset as f64) as usize;
        let c1y = c0y;
        let c2x = ((c0x as f64 + c1x as f64) / 2.0) as usize;
        let c2y = (c0y as f64 + dty - offset as f64) as usize;

        // Store UV coordinates
        tcoords[[tc, 0]] = c0x as f64 / d as f64;
        tcoords[[tc, 1]] = 1.0 - c0y as f64 / d as f64;
        tcoords[[tc, 2]] = c1x as f64 / d as f64;
        tcoords[[tc, 3]] = 1.0 - c1y as f64 / d as f64;
        tcoords[[tc, 4]] = c2x as f64 / d as f64;
        tcoords[[tc, 5]] = 1.0 - c2y as f64 / d as f64;

        // Get vertex and normal indices for this face
        let v0_idx = faces[[tc, 0]].try_into().unwrap_or(0);
        let v1_idx = faces[[tc, 1]].try_into().unwrap_or(0);
        let v2_idx = faces[[tc, 2]].try_into().unwrap_or(0);

        let v0 = vertices.row(v0_idx);
        let v1 = vertices.row(v1_idx);
        let v2 = vertices.row(v2_idx);

        let n0 = normals.row(v0_idx);
        let n1 = normals.row(v1_idx);
        let n2 = normals.row(v2_idx);

        // Sample volume data for each pixel in the triangle
        for y in (c0y.saturating_sub(1))..(c2y + 1).min(d) {
            for x in (c0x.saturating_sub(1))..(c1x + 1).min(d) {
                // Calculate barycentric coordinates
                let bar = uv_to_barycentric(
                    tcoords[[tc, 0]],
                    tcoords[[tc, 1]],
                    tcoords[[tc, 2]],
                    tcoords[[tc, 3]],
                    tcoords[[tc, 4]],
                    tcoords[[tc, 5]],
                    x as f64 / d as f64,
                    1.0 - y as f64 / d as f64,
                );

                let vx = bar[0] * v0[0].into() + bar[1] * v1[0].into() + bar[2] * v2[0].into();
                let vy = bar[0] * v0[1].into() + bar[1] * v1[1].into() + bar[2] * v2[1].into();
                let vz = bar[0] * v0[2].into() + bar[1] * v1[2].into() + bar[2] * v2[2].into();

                // Convert to volume coordinates (FIX: Added spacing division)
                let px = vx / spacing[0];
                let py = vy / spacing[1];
                let pz = vz / spacing[2];

                // Interpolate normal
                let inx = bar[0] * n0[0].into() + bar[1] * n1[0].into() + bar[2] * n2[0].into();
                let iny = bar[0] * n0[1].into() + bar[1] * n1[1].into() + bar[2] * n2[1].into();
                let inz = bar[0] * n0[2].into() + bar[1] * n1[2].into() + bar[2] * n2[2].into();

                // Normalize
                let inn = (inx * inx + iny * iny + inz * inz).sqrt();
                let inx = if inn > 1e-10 { inx / inn } else { 0.0 };
                let iny = if inn > 1e-10 { iny / inn } else { 0.0 };
                let inz = if inn > 1e-10 { inz / inn } else { 0.0 };

                // Sample volume data at this position
                let volume_val = trilinear_interpolate_internal(volume, px, py, pz);
                let surface_hu = volume_val.into() as f64;

                // Apply window/level logic for CLUT index
                let gv = if surface_hu <= min_val {
                    0.0
                } else if surface_hu >= max_val {
                    255.0
                } else {
                    ((surface_hu - (wl - 0.5)) / (ww - 1.0) + 0.5) * 255.0
                };

                let gv_idx = (gv as usize).min(255);

                // Look up opacity from the VR transfer function
                let surface_alpha = lookup_opacity(surface_hu, &opacity_curve);

                // Apply color from CLUT, weighted by opacity
                texture_image[[y, x, 0]] = (clut[[gv_idx, 0]] as f64 * surface_alpha) as u8;
                texture_image[[y, x, 1]] = (clut[[gv_idx, 1]] as f64 * surface_alpha) as u8;
                texture_image[[y, x, 2]] = (clut[[gv_idx, 2]] as f64 * surface_alpha) as u8;

                // Calculate gradient for texture normals
                let h = 1.0;
                let gx1 = trilinear_interpolate_internal(volume, px - h, py, pz);
                let gx2 = trilinear_interpolate_internal(volume, px + h, py, pz);
                let gy1 = trilinear_interpolate_internal(volume, px, py - h, pz);
                let gy2 = trilinear_interpolate_internal(volume, px, py + h, pz);
                let gz1 = trilinear_interpolate_internal(volume, px, py, pz - h);
                let gz2 = trilinear_interpolate_internal(volume, px, py, pz + h);

                let tnx = (gx2.into() - gx1.into()) / (2.0 * h);
                let tny = (gy2.into() - gy1.into()) / (2.0 * h);
                let tnz = (gz2.into() - gz1.into()) / (2.0 * h);

                let tnn = (tnx * tnx + tny * tny + tnz * tnz).sqrt();

                if tnn > 1e-10 {
                    texture_normals[[y, x, 0]] = (((tnx / tnn) + 1.0) * 127.5) as u8;
                    texture_normals[[y, x, 1]] = (((tny / tnn) + 1.0) * 127.5) as u8;
                    texture_normals[[y, x, 2]] = (((tnz / tnn) + 1.0) * 127.5) as u8;
                }

                // MIDA Raycasting (FIX: Corrected offset, steps, and ray init)
                let ray_offset = 50.0;
                let nsteps = 50;
                let step = ray_offset / nsteps as f64;

                let ray_init_x = px + (ray_offset / 2.0) * inx;
                let ray_init_y = py + (ray_offset / 2.0) * iny;
                let ray_init_z = pz + (ray_offset / 2.0) * inz;

                let mut alphai = 0.0;

                // Keep track of floated colors during compositing
                let mut cr = texture_image[[y, x, 0]] as f64;
                let mut cg = texture_image[[y, x, 1]] as f64;
                let mut cb = texture_image[[y, x, 2]] as f64;

                let dx = volume.shape()[2] as f64;
                let dy = volume.shape()[1] as f64;
                let dz = volume.shape()[0] as f64;

                for s in 0..=nsteps {
                    // FIX: Step backwards into the volume
                    let ray_px = ray_init_x - inx * step * s as f64;
                    let ray_py = ray_init_y - iny * step * s as f64;
                    let ray_pz = ray_init_z - inz * step * s as f64;

                    if ray_px >= 0.0
                        && ray_px <= (dx - 1.0)
                        && ray_py >= 0.0
                        && ray_py <= (dy - 1.0)
                        && ray_pz >= 0.0
                        && ray_pz <= (dz - 1.0)
                    {
                        let ray_val =
                            trilinear_interpolate_internal(volume, ray_px, ray_py, ray_pz);
                        let val = ray_val.into() as f64;

                        // Map raw HU to CLUT index via WW/WL
                        let ray_gv = if val <= min_val {
                            0.0
                        } else if val >= max_val {
                            255.0
                        } else {
                            ((val - (wl - 0.5)) / (ww - 1.0) + 0.5) * 255.0
                        };

                        let ray_gv_idx = (ray_gv as usize).min(255);
                        // Use VR opacity transfer function instead of linear ramp
                        let alpha = lookup_opacity(val, &opacity_curve);

                        cr += clut[[ray_gv_idx, 0]] as f64 * alpha * (1.0 - alphai);
                        cg += clut[[ray_gv_idx, 1]] as f64 * alpha * (1.0 - alphai);
                        cb += clut[[ray_gv_idx, 2]] as f64 * alpha * (1.0 - alphai);

                        alphai = (1.0 - alphai) * alpha + alphai;
                        if alphai >= 1.0 {
                            break;
                        }
                    }
                }

                texture_image[[y, x, 0]] = cr.min(255.0) as u8;
                texture_image[[y, x, 1]] = cg.min(255.0) as u8;
                texture_image[[y, x, 2]] = cb.min(255.0) as u8;
            }
        }
    }

    (tcoords, texture_image, texture_normals)
}

/// Generate UV coordinates and texture from volume (without color mapping)
pub fn generate_tcoords_internal<V, F, T>(
    vertices: ArrayView2<V>,
    faces: ArrayView2<F>,
    volume: ArrayView3<T>,
    spacing: &[f64; 3],
    texture_dim: usize,
) -> (Array2<f64>, Array2<i16>, Array3<u8>)
where
    V: Copy + Into<f64> + Send + Sync,
    F: Copy + TryInto<usize> + Send + Sync,
    T: Copy + Into<f64> + Send + Sync + NumCast,
{
    let n_faces = faces.shape()[0];

    let nx = (n_faces as f64).sqrt() as usize;
    let ny = (n_faces as f64 / nx as f64).ceil() as usize;

    let d = texture_dim;
    let dtx = d as f64 / nx as f64;
    let dty = d as f64 / ny as f64;

    let offset = 2;

    let mut tcoords = Array2::<f64>::zeros((n_faces, 6));
    let mut texture_image = Array2::<i16>::zeros((d, d)); // 2D grayscale
    let mut texture_normals = Array3::<u8>::zeros((d, d, 3));

    let h = 1.0;

    for tc in 0..n_faces {
        let i = tc % nx;
        let j = tc / nx;

        let c0x = (i as f64 * dtx + offset as f64) as usize;
        let c0y = (j as f64 * dty + offset as f64) as usize;
        let c1x = (c0x as f64 + dtx - offset as f64) as usize;
        let c1y = c0y;
        let c2x = ((c0x as f64 + c1x as f64) / 2.0) as usize;
        let c2y = (c0y as f64 + dty - offset as f64) as usize;

        tcoords[[tc, 0]] = c0x as f64 / d as f64;
        tcoords[[tc, 1]] = 1.0 - c0y as f64 / d as f64;
        tcoords[[tc, 2]] = c1x as f64 / d as f64;
        tcoords[[tc, 3]] = 1.0 - c1y as f64 / d as f64;
        tcoords[[tc, 4]] = c2x as f64 / d as f64;
        tcoords[[tc, 5]] = 1.0 - c2y as f64 / d as f64;

        let v0_idx = faces[[tc, 0]].try_into().unwrap_or(0);
        let v1_idx = faces[[tc, 1]].try_into().unwrap_or(0);
        let v2_idx = faces[[tc, 2]].try_into().unwrap_or(0);

        let v0 = vertices.row(v0_idx);
        let v1 = vertices.row(v1_idx);
        let v2 = vertices.row(v2_idx);

        for y in c0y.saturating_sub(1)..(c2y + 1).min(d) {
            for x in c0x.saturating_sub(1)..(c1x + 1).min(d) {
                let bar = uv_to_barycentric(
                    tcoords[[tc, 0]],
                    tcoords[[tc, 1]],
                    tcoords[[tc, 2]],
                    tcoords[[tc, 3]],
                    tcoords[[tc, 4]],
                    tcoords[[tc, 5]],
                    x as f64 / d as f64,
                    1.0 - y as f64 / d as f64,
                );

                let vx = bar[0] * v0[0].into() + bar[1] * v1[0].into() + bar[2] * v2[0].into();
                let vy = bar[0] * v0[1].into() + bar[1] * v1[1].into() + bar[2] * v2[1].into();
                let vz = bar[0] * v0[2].into() + bar[1] * v1[2].into() + bar[2] * v2[2].into();

                let px = vx / spacing[0];
                let py = vy / spacing[1];
                let pz = vz / spacing[2];

                // Sample volume at multiple points for averaging
                let gv = (trilinear_interpolate_internal(volume, px, py, pz).into()
                    + trilinear_interpolate_internal(volume, px + h, py, pz).into()
                    + trilinear_interpolate_internal(volume, px - h, py, pz).into()
                    + trilinear_interpolate_internal(volume, px, py + h, pz).into()
                    + trilinear_interpolate_internal(volume, px, py - h, pz).into()
                    + trilinear_interpolate_internal(volume, px, py, pz + h).into()
                    + trilinear_interpolate_internal(volume, px, py, pz - h).into())
                    / 7.0;

                // Compute gradient for texture normals
                let tnx = (trilinear_interpolate_internal(volume, px + h, py, pz).into()
                    - trilinear_interpolate_internal(volume, px - h, py, pz).into())
                    / (2.0 * h);
                let tny = (trilinear_interpolate_internal(volume, px, py + h, pz).into()
                    - trilinear_interpolate_internal(volume, px, py - h, pz).into())
                    / (2.0 * h);
                let tnz = (trilinear_interpolate_internal(volume, px, py, pz + h).into()
                    - trilinear_interpolate_internal(volume, px, py, pz - h).into())
                    / (2.0 * h);

                let tnn = (tnx * tnx + tny * tny + tnz * tnz).sqrt();

                texture_image[[y, x]] = gv as i16; // 2D indexing

                if tnn > 1e-10 {
                    texture_normals[[y, x, 0]] = (((tnx / tnn) + 1.0) * 127.5) as u8;
                    texture_normals[[y, x, 1]] = (((tny / tnn) + 1.0) * 127.5) as u8;
                    texture_normals[[y, x, 2]] = (((tnz / tnn) + 1.0) * 127.5) as u8;
                }
            }
        }
    }

    (tcoords, texture_image, texture_normals)
}

/// High-frequency surface texture using multi-slice raycasting
pub fn generate_tcoords_hf_internal<V, F, T>(
    vertices: ArrayView2<V>,
    normals: ArrayView2<V>,
    faces: ArrayView2<F>,
    volume: ArrayView3<T>,
    spacing: &[f64; 3],
    window_width: i32,
    window_level: i32,
    clut: ArrayView2<u8>,
    texture_dim: usize,
    n_slices: usize,
) -> (Array2<f64>, Array3<i16>, Array3<u8>)
where
    V: Copy + Into<f64> + Send + Sync,
    F: Copy + TryInto<usize> + Send + Sync,
    T: Copy + Into<f64> + Send + Sync + NumCast,
{
    let n_faces = faces.shape()[0];

    let nx = (n_faces as f64).sqrt() as usize;
    let ny = (n_faces as f64 / nx as f64).ceil() as usize;

    let d = texture_dim;
    let dtx = d as f64 / nx as f64;
    let dty = d as f64 / ny as f64;

    let offset = 2;
    let ray_offset = 5.0;

    let mut tcoords = Array2::<f64>::zeros((n_faces, 6));
    let mut texture_image = Array3::<i16>::from_elem((n_slices, d, d), -32768);
    let mut texture_normals = Array3::<u8>::zeros((d, d, 3));

    for tc in 0..n_faces {
        let i = tc % nx;
        let j = tc / nx;

        let c0x = (i as f64 * dtx + offset as f64) as usize;
        let c0y = (j as f64 * dty + offset as f64) as usize;
        let c1x = (c0x as f64 + dtx - offset as f64) as usize;
        let c1y = c0y;
        let c2x = ((c0x as f64 + c1x as f64) / 2.0) as usize;
        let c2y = (c0y as f64 + dty - offset as f64) as usize;

        tcoords[[tc, 0]] = c0x as f64 / d as f64;
        tcoords[[tc, 1]] = 1.0 - c0y as f64 / d as f64;
        tcoords[[tc, 2]] = c1x as f64 / d as f64;
        tcoords[[tc, 3]] = 1.0 - c1y as f64 / d as f64;
        tcoords[[tc, 4]] = c2x as f64 / d as f64;
        tcoords[[tc, 5]] = 1.0 - c2y as f64 / d as f64;

        let v0_idx = faces[[tc, 0]].try_into().unwrap_or(0);
        let v1_idx = faces[[tc, 1]].try_into().unwrap_or(0);
        let v2_idx = faces[[tc, 2]].try_into().unwrap_or(0);

        let v0 = vertices.row(v0_idx);
        let v1 = vertices.row(v1_idx);
        let v2 = vertices.row(v2_idx);

        let n0 = normals.row(v0_idx);
        let n1 = normals.row(v1_idx);
        let n2 = normals.row(v2_idx);

        for y in c0y.saturating_sub(1)..(c2y + 1).min(d) {
            for x in c0x.saturating_sub(1)..(c1x + 1).min(d) {
                let bar = uv_to_barycentric(
                    tcoords[[tc, 0]],
                    tcoords[[tc, 1]],
                    tcoords[[tc, 2]],
                    tcoords[[tc, 3]],
                    tcoords[[tc, 4]],
                    tcoords[[tc, 5]],
                    x as f64 / d as f64,
                    1.0 - y as f64 / d as f64,
                );

                let vx = bar[0] * v0[0].into() + bar[1] * v1[0].into() + bar[2] * v2[0].into();
                let vy = bar[0] * v0[1].into() + bar[1] * v1[1].into() + bar[2] * v2[1].into();
                let vz = bar[0] * v0[2].into() + bar[1] * v1[2].into() + bar[2] * v2[2].into();

                let px = vx;
                let py = vy;
                let pz = vz;

                // Interpolate normal
                let inx = bar[0] * n0[0].into() + bar[1] * n1[0].into() + bar[2] * n2[0].into();
                let iny = bar[0] * n0[1].into() + bar[1] * n1[1].into() + bar[2] * n2[1].into();
                let inz = bar[0] * n0[2].into() + bar[1] * n1[2].into() + bar[2] * n2[2].into();

                let inn = (inx * inx + iny * iny + inz * inz).sqrt();
                let inx = if inn > 1e-10 { inx / inn } else { 0.0 };
                let iny = if inn > 1e-10 { iny / inn } else { 0.0 };
                let inz = if inn > 1e-10 { inz / inn } else { 0.0 };

                // Multi-slice raycasting (negative normal direction)
                let step = ray_offset / n_slices as f64;

                for s in 0..n_slices {
                    let ray_px = (px - inx * step * s as f64) / spacing[0];
                    let ray_py = (py - iny * step * s as f64) / spacing[1];
                    let ray_pz = (pz - inz * step * s as f64) / spacing[2];

                    let dx = volume.shape()[2] as f64;
                    let dy = volume.shape()[1] as f64;
                    let dz = volume.shape()[0] as f64;

                    if ray_px >= 0.0
                        && ray_px <= (dx - 1.0)
                        && ray_py >= 0.0
                        && ray_py <= (dy - 1.0)
                        && ray_pz >= 0.0
                        && ray_pz <= (dz - 1.0)
                    {
                        let vol_val = crate::interpolation::tricubic_interpolate_internal(
                            volume, ray_px, ray_py, ray_pz,
                        );
                        texture_image[[s, y, x]] = <i16 as NumCast>::from(vol_val).unwrap_or(0);
                    } else {
                        texture_image[[s, y, x]] = -32768; // NULL_VALUE
                    }
                }

                let px = px / spacing[0];
                let py = py / spacing[1];
                let pz = pz / spacing[2];

                // Compute gradient normals
                let h = 1.0;
                let gx1 = trilinear_interpolate_internal(volume, px - h, py, pz);
                let gx2 = trilinear_interpolate_internal(volume, px + h, py, pz);
                let gy1 = trilinear_interpolate_internal(volume, px, py - h, pz);
                let gy2 = trilinear_interpolate_internal(volume, px, py + h, pz);
                let gz1 = trilinear_interpolate_internal(volume, px, py, pz - h);
                let gz2 = trilinear_interpolate_internal(volume, px, py, pz + h);

                let tnx = (gx2.into() - gx1.into()) / (2.0 * h);
                let tny = (gy2.into() - gy1.into()) / (2.0 * h);
                let tnz = (gz2.into() - gz1.into()) / (2.0 * h);

                let tnn = (tnx * tnx + tny * tny + tnz * tnz).sqrt();

                if tnn > 1e-10 {
                    texture_normals[[y, x, 0]] = (((tnx / tnn) + 1.0) * 127.5) as u8;
                    texture_normals[[y, x, 1]] = (((tny / tnn) + 1.0) * 127.5) as u8;
                    texture_normals[[y, x, 2]] = (((tnz / tnn) + 1.0) * 127.5) as u8;
                }
            }
        }
    }

    (tcoords, texture_image, texture_normals)
}
