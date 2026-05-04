use nalgebra::Matrix4;
use ndarray::parallel::prelude::*;
use ndarray::{ArrayView3, ArrayViewMut3};
use num_traits::NumCast;
use numpy::{PyReadonlyArray2, PyReadonlyArray3, ToPyArray};
use pyo3::exceptions::PyTypeError;
use pyo3::prelude::*;

use crate::transforms::coord_transform;
use crate::types::{ImageTypes3, ImageTypesMut3};

pub fn apply_view_matrix_transform_internal<
    T: Copy + Into<f64> + NumCast + PartialOrd + Send + Sync,
>(
    volume: ArrayView3<T>,
    spacing: [f64; 3],
    m: PyReadonlyArray2<f64>,
    n: usize,
    orientation: String,
    minterpol: i32,
    cval: T,
    mut out: ArrayViewMut3<T>,
) -> PyResult<()> {
    let m_slice = m.as_slice().unwrap();
    let m_nalgebra = Matrix4::from_row_slice(m_slice);

    let (sx, sy, sz) = (spacing[0], spacing[1], spacing[2]);

    par_azip!((index (cz,cy,cx), val in &mut out) {
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
        *val = coord_transform(volume, &m_nalgebra, x, y, z, sx, sy, sz, minterpol, cval);
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

#[pyfunction]
pub fn apply_view_matrix_transform<'py>(
    volume: ImageTypes3<'py>,
    spacing: [f64; 3],
    m: PyReadonlyArray2<f64>,
    n: usize,
    orientation: String,
    minterpol: i32,
    cval: Bound<'py, PyAny>,
    out: ImageTypesMut3<'py>,
) -> PyResult<()> {
    match (volume, out) {
        (ImageTypes3::I16(volume), ImageTypesMut3::I16(mut out)) => {
            apply_view_matrix_transform_internal(
                volume.as_array(),
                spacing,
                m,
                n,
                orientation,
                minterpol,
                cval.extract::<i16>()?,
                out.as_array_mut(),
            )?;
            Ok(())
        }
        (ImageTypes3::U8(volume), ImageTypesMut3::U8(mut out)) => {
            apply_view_matrix_transform_internal(
                volume.as_array(),
                spacing,
                m,
                n,
                orientation,
                minterpol,
                cval.extract::<u8>()?,
                out.as_array_mut(),
            )?;
            Ok(())
        }
        (ImageTypes3::F64(volume), ImageTypesMut3::F64(mut out)) => {
            apply_view_matrix_transform_internal(
                volume.as_array(),
                spacing,
                m,
                n,
                orientation,
                minterpol,
                cval.extract::<f64>()?,
                out.as_array_mut(),
            )?;
            Ok(())
        }
        _ => Err(PyTypeError::new_err("Invalid volume or output type")),
    }
}
