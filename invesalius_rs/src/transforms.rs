use nalgebra::{Matrix4, Vector4};
use numpy::{PyReadonlyArray3, PyReadwriteArray3, PyReadonlyArray2, ToPyArray, PyUntypedArrayMethods, ndarray};
use pyo3::prelude::*;
use ndarray::parallel::prelude::*;

use crate::interpolation::{trilinear_interpolate_internal, tricubic_interpolate_internal, lanczos_interpolate_internal};

fn coord_transform(
    volume: &ndarray::ArrayView3<i16>,
    m: &Matrix4<f64>,
    x: usize,
    y: usize,
    z: usize,
    sx: f64,
    sy: f64,
    sz: f64,
    minterpol: i32,
    cval: i16,
) -> i16 {
    let coord = Vector4::new(z as f64 * sz, y as f64 * sy, x as f64 * sx, 1.0);
    let ncoord = m * coord;

    let dims = volume.shape();
    let (dz, dy, dx) = (dims[0] as f64, dims[1] as f64, dims[2] as f64);

    let nz = (ncoord[0] / ncoord[3]) / sz;
    let ny = (ncoord[1] / ncoord[3]) / sy;
    let nx = (ncoord[2] / ncoord[3]) / sx;

    if nz >= 0.0 && nz < dz - 1.0 && ny >= 0.0 && ny < dy - 1.0 && nx >= 0.0 && nx < dx - 1.0 {
        let v = match minterpol {
            0 => volume[[nz as usize, ny as usize, nx as usize]] as f64,
            1 => trilinear_interpolate_internal(volume, nx, ny, nz),
            2 => {
                let v = tricubic_interpolate_internal(volume, nx, ny, nz);
                if v < cval as f64 { cval as f64 } else { v }
            }
            _ => {
                let v = lanczos_interpolate_internal(volume, nx, ny, nz);
                if v < cval as f64 { cval as f64 } else { v }
            }
        };
        v as i16
    } else {
        cval
    }
}

#[pyfunction]
pub fn apply_view_matrix_transform(
    volume: PyReadonlyArray3<i16>,
    spacing: [f64; 3],
    m: PyReadonlyArray2<f64>,
    n: usize,
    orientation: String,
    minterpol: i32,
    cval: i16,
    mut out: PyReadwriteArray3<i16>,
) -> PyResult<()> {
    let volume_arr = volume.as_array();
    let m_slice = m.as_slice().unwrap();
    let m_nalgebra = Matrix4::from_row_slice(m_slice);

    let (sx, sy, sz) = (spacing[0], spacing[1], spacing[2]);
    
    let volume_dims = volume_arr.shape();
    let (dz, dy, dx) = (volume_dims[0], volume_dims[1], volume_dims[2]);
    
    let out_dims = out.shape().to_vec();
    let (odz, ody, odx) = (out_dims[0], out_dims[1], out_dims[2]);

    let mut out_arr = out.as_array_mut();

    par_azip!((index (cz,cy,cx), val in &mut out_arr) {
        let mut z = cz;
        let mut y = cy;
        let mut x = cx;
        match orientation.as_str() {
            "AXIAL" => {
                z = n + cz;
            }
            "CORONAL" => {
                y = n + cy;
            }
            "SAGITAL" => {
                x = n + cx;
            }
            _ => (),
        }
        *val = coord_transform(&volume_arr, &m_nalgebra, x, y, z, sx, sy, sz, minterpol, cval);
    });
    
    Ok(())
}

#[pyfunction]
pub fn convolve_non_zero(
    py: Python,
    volume: PyReadonlyArray3<f64>,
    kernel: PyReadonlyArray3<f64>,
    cval: i16,
) -> PyResult<Py<PyAny>> {
    let volume_arr = volume.as_array();
    let kernel_arr = kernel.as_array();
    
    let volume_dims = volume_arr.shape();
    let (sz, sy, sx) = (volume_dims[0], volume_dims[1], volume_dims[2]);

    let kernel_dims = kernel_arr.shape();
    let (skz, sky, skx) = (kernel_dims[0], kernel_dims[1], kernel_dims[2]);

    let mut out_arr = ndarray::Array3::<f64>::zeros((sz, sy, sx));

    println!("\n\nConvolving non-zero values!\n\n");

    par_azip!((index (z, y, x), val in &mut out_arr) {
        if volume_arr[[z, y, x]] != 0.0 {
            let mut sum = 0.0f64;
            for k in 0..skz {
                let kz = z as isize - (skz / 2) as isize + k as isize;
                for j in 0..sky {
                    let ky = y as isize - (sky / 2) as isize + j as isize;
                    for i in 0..skx {
                        let kx = x as isize - (skx / 2) as isize + i as isize;
                        let v = if kz >= 0 && kz < sz as isize && ky >= 0 && ky < sy as isize && kx >= 0 && kx < sx as isize {
                            volume_arr[[kz as usize, ky as usize, kx as usize]]
                        } else {
                            cval as f64
                        };
                        sum += v * kernel_arr[[k, j, i]];
                    }
                }
            }
            *val = sum;
        }
    });
    Ok(out_arr.to_pyarray(py).to_owned().into())
}