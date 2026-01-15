use numpy::{PyReadonlyArray3, ndarray};
use pyo3::prelude::*;
use std::f64::consts::PI;

// Helper function to get value with boundary wrapping
fn get_value<T: Copy + Into<f64>>(v: &ndarray::ArrayView3<T>, x: isize, y: isize, z: isize) -> f64 {
    let dims = v.shape();
    let dz = dims[0] as isize;
    let dy = dims[1] as isize;
    let dx = dims[2] as isize;

    let mut z_idx = z;
    let mut y_idx = y;
    let mut x_idx = x;

    if x_idx < 0 {
        x_idx = dx + x_idx;
    } else if x_idx >= dx {
        x_idx = x_idx - dx;
    }

    if y_idx < 0 {
        y_idx = dy + y_idx;
    } else if y_idx >= dy {
        y_idx = y_idx - dy;
    }

    if z_idx < 0 {
        z_idx = dz + z_idx;
    } else if z_idx >= dz {
        z_idx = z_idx - dz;
    }

    v[[z_idx as usize, y_idx as usize, x_idx as usize]].into()
}

#[pyfunction]
pub fn nearest_neighbour_interp(
    v: PyReadonlyArray3<i16>,
    x: f64,
    y: f64,
    z: f64,
) -> PyResult<f64> {
    let arr = v.as_array();
    Ok(arr[[z as usize, y as usize, x as usize]] as f64)
}

#[pyfunction]
pub fn trilin_interpolate_py(
    v: PyReadonlyArray3<i16>,
    x: f64,
    y: f64,
    z: f64,
) -> PyResult<f64> {
    let arr = v.as_array();
    
    let x0 = x.floor() as isize;
    let x1 = x0 + 1;
    let y0 = y.floor() as isize;
    let y1 = y0 + 1;
    let z0 = z.floor() as isize;
    let z1 = z0 + 1;

    let xd = x - x0 as f64;
    let yd = y - y0 as f64;
    let zd = z - z0 as f64;

    let v000 = get_value(&arr, x0, y0, z0);
    let v100 = get_value(&arr, x1, y0, z0);
    let v010 = get_value(&arr, x0, y1, z0);
    let v001 = get_value(&arr, x0, y0, z1);
    let v110 = get_value(&arr, x1, y1, z0);
    let v101 = get_value(&arr, x1, y0, z1);
    let v011 = get_value(&arr, x0, y1, z1);
    let v111 = get_value(&arr, x1, y1, z1);

    let c00 = v000 * (1.0 - xd) + v100 * xd;
    let c10 = v010 * (1.0 - xd) + v110 * xd;
    let c01 = v001 * (1.0 - xd) + v101 * xd;
    let c11 = v011 * (1.0 - xd) + v111 * xd;

    let c0 = c00 * (1.0 - yd) + c10 * yd;
    let c1 = c01 * (1.0 - yd) + c11 * yd;

    Ok(c0 * (1.0 - zd) + c1 * zd)
}

fn cubic_interpolate(p: [f64; 4], x: f64) -> f64 {
    p[1] + 0.5 * x * (p[2] - p[0] + x * (2.0 * p[0] - 5.0 * p[1] + 4.0 * p[2] - p[3] + x * (3.0 * (p[1] - p[2]) + p[3] - p[0])))
}

fn bicubic_interpolate(p: [[f64; 4]; 4], x: f64, y: f64) -> f64 {
    let mut arr = [0.0; 4];
    arr[0] = cubic_interpolate(p[0], y);
    arr[1] = cubic_interpolate(p[1], y);
    arr[2] = cubic_interpolate(p[2], y);
    arr[3] = cubic_interpolate(p[3], y);
    cubic_interpolate(arr, x)
}

#[pyfunction]
pub fn tricub_interpolate_py(
    v: PyReadonlyArray3<i16>,
    x: f64,
    y: f64,
    z: f64,
) -> PyResult<f64> {
    let arr = v.as_array();
    
    let xi = x.floor() as isize;
    let yi = y.floor() as isize;
    let zi = z.floor() as isize;

    let mut p = [[[0.0; 4]; 4]; 4];

    for i in 0..4 {
        for j in 0..4 {
            for k in 0..4 {
                p[i][j][k] = get_value(&arr, xi + i as isize - 1, yi + j as isize - 1, zi + k as isize - 1);
            }
        }
    }

    let mut arr_result = [0.0; 4];
    arr_result[0] = bicubic_interpolate(p[0], y - yi as f64, z - zi as f64);
    arr_result[1] = bicubic_interpolate(p[1], y - yi as f64, z - zi as f64);
    arr_result[2] = bicubic_interpolate(p[2], y - yi as f64, z - zi as f64);
    arr_result[3] = bicubic_interpolate(p[3], y - yi as f64, z - zi as f64);
    
    Ok(cubic_interpolate(arr_result, x - xi as f64))
}

#[pyfunction]
pub fn tricub_interpolate2_py(
    v: PyReadonlyArray3<i16>,
    x: f64,
    y: f64,
    z: f64,
) -> PyResult<f64> {
    // Same as tricub_interpolate_py - alternate implementation
    tricub_interpolate_py(v, x, y, z)
}

// Lanczos interpolation
fn lanczos_kernel(x: f64, a: i32) -> f64 {
    if x == 0.0 {
        1.0
    } else if -a as f64 <= x && x < a as f64 {
        let a_f = a as f64;
        (a_f * (PI * x).sin() * (PI * (x / a_f)).sin()) / (PI * PI * x * x)
    } else {
        0.0
    }
}

#[pyfunction]
pub fn lanczos_interpolate_py(
    v: PyReadonlyArray3<i16>,
    x: f64,
    y: f64,
    z: f64,
) -> PyResult<f64> {
    let arr = v.as_array();
    let a = 4i32; // Lanczos window size
    
    let xd = x.floor() as isize;
    let yd = y.floor() as isize;
    let zd = z.floor() as isize;

    let xi = xd - a as isize + 1;
    let xf = xd + a as isize;
    let yi = yd - a as isize + 1;
    let yf = yd + a as isize;
    let zi = zd - a as isize + 1;
    let zf = zd + a as isize;

    let size = (2 * a - 1) as usize;
    let mut temp_x = vec![vec![0.0; size]; size];
    let mut temp_y = vec![0.0; size];

    let mut m = 0usize;
    for kk in zi..zf {
        let mut n = 0usize;
        for jj in yi..yf {
            let mut lx = 0.0;
            for ii in xi..xf {
                lx += get_value(&arr, ii, jj, kk) * lanczos_kernel(x - ii as f64, a);
            }
            temp_x[m][n] = lx;
            n += 1;
        }
        m += 1;
    }

    m = 0;
    for _ in zi..zf {
        let mut n = 0usize;
        let mut ly = 0.0;
        for jj in yi..yf {
            ly += temp_x[m][n] * lanczos_kernel(y - jj as f64, a);
            n += 1;
        }
        temp_y[m] = ly;
        m += 1;
    }

    let mut lz = 0.0;
    m = 0;
    for kk in zi..zf {
        lz += temp_y[m] * lanczos_kernel(z - kk as f64, a);
        m += 1;
    }

    Ok(lz)
}

// Internal functions for use by transforms module
pub fn trilinear_interpolate_internal(arr: &ndarray::ArrayView3<i16>, x: f64, y: f64, z: f64) -> f64 {
    let x0 = x.floor() as isize;
    let x1 = x0 + 1;
    let y0 = y.floor() as isize;
    let y1 = y0 + 1;
    let z0 = z.floor() as isize;
    let z1 = z0 + 1;

    let xd = x - x0 as f64;
    let yd = y - y0 as f64;
    let zd = z - z0 as f64;

    let v000 = get_value(arr, x0, y0, z0);
    let v100 = get_value(arr, x1, y0, z0);
    let v010 = get_value(arr, x0, y1, z0);
    let v001 = get_value(arr, x0, y0, z1);
    let v110 = get_value(arr, x1, y1, z0);
    let v101 = get_value(arr, x1, y0, z1);
    let v011 = get_value(arr, x0, y1, z1);
    let v111 = get_value(arr, x1, y1, z1);

    let c00 = v000 * (1.0 - xd) + v100 * xd;
    let c10 = v010 * (1.0 - xd) + v110 * xd;
    let c01 = v001 * (1.0 - xd) + v101 * xd;
    let c11 = v011 * (1.0 - xd) + v111 * xd;

    let c0 = c00 * (1.0 - yd) + c10 * yd;
    let c1 = c01 * (1.0 - yd) + c11 * yd;

    c0 * (1.0 - zd) + c1 * zd
}

pub fn tricubic_interpolate_internal(arr: &ndarray::ArrayView3<i16>, x: f64, y: f64, z: f64) -> f64 {
    let xi = x.floor() as isize;
    let yi = y.floor() as isize;
    let zi = z.floor() as isize;

    let mut p = [[[0.0; 4]; 4]; 4];

    for i in 0..4 {
        for j in 0..4 {
            for k in 0..4 {
                p[i][j][k] = get_value(arr, xi + i as isize - 1, yi + j as isize - 1, zi + k as isize - 1);
            }
        }
    }

    let mut arr_result = [0.0; 4];
    arr_result[0] = bicubic_interpolate(p[0], y - yi as f64, z - zi as f64);
    arr_result[1] = bicubic_interpolate(p[1], y - yi as f64, z - zi as f64);
    arr_result[2] = bicubic_interpolate(p[2], y - yi as f64, z - zi as f64);
    arr_result[3] = bicubic_interpolate(p[3], y - yi as f64, z - zi as f64);
    
    cubic_interpolate(arr_result, x - xi as f64)
}

pub fn lanczos_interpolate_internal(arr: &ndarray::ArrayView3<i16>, x: f64, y: f64, z: f64) -> f64 {
    let a = 4i32;
    
    let xd = x.floor() as isize;
    let yd = y.floor() as isize;
    let zd = z.floor() as isize;

    let xi = xd - a as isize + 1;
    let xf = xd + a as isize;
    let yi = yd - a as isize + 1;
    let yf = yd + a as isize;
    let zi = zd - a as isize + 1;
    let zf = zd + a as isize;

    let size = (2 * a - 1) as usize;
    let mut temp_x = vec![vec![0.0; size]; size];
    let mut temp_y = vec![0.0; size];

    let mut m = 0usize;
    for kk in zi..zf {
        let mut n = 0usize;
        for jj in yi..yf {
            let mut lx = 0.0;
            for ii in xi..xf {
                lx += get_value(arr, ii, jj, kk) * lanczos_kernel(x - ii as f64, a);
            }
            temp_x[m][n] = lx;
            n += 1;
        }
        m += 1;
    }

    m = 0;
    for _ in zi..zf {
        let mut n = 0usize;
        let mut ly = 0.0;
        for jj in yi..yf {
            ly += temp_x[m][n] * lanczos_kernel(y - jj as f64, a);
            n += 1;
        }
        temp_y[m] = ly;
        m += 1;
    }

    let mut lz = 0.0;
    m = 0;
    for kk in zi..zf {
        lz += temp_y[m] * lanczos_kernel(z - kk as f64, a);
        m += 1;
    }

    lz
}
