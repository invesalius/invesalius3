use nalgebra::{Matrix4, Vector4};
use ndarray::ArrayView3;
use num_traits::NumCast;

use crate::interpolation::{
    lanczos_interpolate_internal, tricubic_interpolate_internal, trilinear_interpolate_internal,
};

pub(crate) fn coord_transform<T: Copy + Into<f64> + NumCast + PartialOrd>(
    volume: ArrayView3<T>,
    m: &Matrix4<f64>,
    x: usize,
    y: usize,
    z: usize,
    sx: f64,
    sy: f64,
    sz: f64,
    minterpol: i32,
    cval: T,
) -> T {
    let coord = Vector4::new(z as f64 * sz, y as f64 * sy, x as f64 * sx, 1.0);
    let ncoord = m * coord;

    let dims = volume.shape();
    let (dz, dy, dx) = (dims[0] as f64, dims[1] as f64, dims[2] as f64);

    let nz = (ncoord[0] / ncoord[3]) / sz;
    let ny = (ncoord[1] / ncoord[3]) / sy;
    let nx = (ncoord[2] / ncoord[3]) / sx;

    if nz >= 0.0 && nz < dz - 1.0 && ny >= 0.0 && ny < dy - 1.0 && nx >= 0.0 && nx < dx - 1.0 {
        match minterpol {
            0 => volume[[nz as usize, ny as usize, nx as usize]],
            1 => trilinear_interpolate_internal(volume, nx, ny, nz),
            2 => {
                let v = tricubic_interpolate_internal(volume, nx, ny, nz);
                if v < cval {
                    cval
                } else {
                    v
                }
            }
            _ => {
                let v = lanczos_interpolate_internal(volume, nx, ny, nz);
                if v < cval {
                    cval
                } else {
                    v
                }
            }
        }
    } else {
        cval
    }
}
