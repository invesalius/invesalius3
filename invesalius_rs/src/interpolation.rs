use ndarray::ArrayView3;
use num_traits::NumCast;
use std::f64::consts::PI;

// Helper function to get value with boundary wrapping
fn get_value<T: Copy + Into<f64>>(v: ArrayView3<T>, x: isize, y: isize, z: isize) -> T {
    let dims = v.shape();
    let dz = dims[0] as isize;
    let dy = dims[1] as isize;
    let dx = dims[2] as isize;

    let mut z_idx = z;
    let mut y_idx = y;
    let mut x_idx = x;

    if x_idx < 0 {
        x_idx += dx;
    } else if x_idx >= dx {
        x_idx -= dx;
    }

    if y_idx < 0 {
        y_idx += dy;
    } else if y_idx >= dy {
        y_idx -= dy;
    }

    if z_idx < 0 {
        z_idx += dz;
    } else if z_idx >= dz {
        z_idx -= dz;
    }

    v[[z_idx as usize, y_idx as usize, x_idx as usize]]
}

fn cubic_interpolate(p: [f64; 4], x: f64) -> f64 {
    p[1] + 0.5
        * x
        * (p[2] - p[0]
            + x * (2.0 * p[0] - 5.0 * p[1] + 4.0 * p[2] - p[3]
                + x * (3.0 * (p[1] - p[2]) + p[3] - p[0])))
}

fn bicubic_interpolate(p: [[f64; 4]; 4], x: f64, y: f64) -> f64 {
    let mut arr = [0.0; 4];
    arr[0] = cubic_interpolate(p[0], y);
    arr[1] = cubic_interpolate(p[1], y);
    arr[2] = cubic_interpolate(p[2], y);
    arr[3] = cubic_interpolate(p[3], y);
    cubic_interpolate(arr, x)
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

// Internal functions for use by transforms module
pub fn trilinear_interpolate_internal<T: Copy + Into<f64> + NumCast>(
    arr: ArrayView3<T>,
    x: f64,
    y: f64,
    z: f64,
) -> T {
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

    let c00 = v000.into() * (1.0 - xd) + v100.into() * xd;
    let c10 = v010.into() * (1.0 - xd) + v110.into() * xd;
    let c01 = v001.into() * (1.0 - xd) + v101.into() * xd;
    let c11 = v011.into() * (1.0 - xd) + v111.into() * xd;

    let c0 = c00 * (1.0 - yd) + c10 * yd;
    let c1 = c01 * (1.0 - yd) + c11 * yd;

    let result = c0 * (1.0 - zd) + c1 * zd;
    NumCast::from(result).unwrap()
}

pub fn tricubic_interpolate_internal<T: Copy + Into<f64> + NumCast>(
    arr: ArrayView3<T>,
    x: f64,
    y: f64,
    z: f64,
) -> T {
    let xi = x.floor() as isize;
    let yi = y.floor() as isize;
    let zi = z.floor() as isize;

    let mut p = [[[0.0; 4]; 4]; 4];

    for (i, plane) in p.iter_mut().enumerate() {
        for (j, row) in plane.iter_mut().enumerate() {
            for (k, val) in row.iter_mut().enumerate() {
                *val = get_value(
                    arr,
                    xi + i as isize - 1,
                    yi + j as isize - 1,
                    zi + k as isize - 1,
                )
                .into();
            }
        }
    }

    let mut arr_result = [0.0; 4];
    arr_result[0] = bicubic_interpolate(p[0], y - yi as f64, z - zi as f64);
    arr_result[1] = bicubic_interpolate(p[1], y - yi as f64, z - zi as f64);
    arr_result[2] = bicubic_interpolate(p[2], y - yi as f64, z - zi as f64);
    arr_result[3] = bicubic_interpolate(p[3], y - yi as f64, z - zi as f64);

    <T as NumCast>::from(cubic_interpolate(arr_result, x - xi as f64)).unwrap()
}

pub fn lanczos_interpolate_internal<T: Copy + Into<f64> + NumCast>(
    arr: ArrayView3<T>,
    x: f64,
    y: f64,
    z: f64,
) -> T {
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

    let _m = 0usize;
    for (m, kk) in (zi..zf).enumerate() {
        for (n, jj) in (yi..yf).enumerate() {
            let mut lx = 0.0;
            for ii in xi..xf {
                lx += get_value(arr, ii, jj, kk).into() * lanczos_kernel(x - ii as f64, a);
            }
            temp_x[m][n] = lx;
        }
    }

    for (m, _kk) in (zi..zf).enumerate() {
        let mut ly = 0.0;
        for (n, jj) in (yi..yf).enumerate() {
            ly += temp_x[m][n] * lanczos_kernel(y - jj as f64, a);
        }
        temp_y[m] = ly;
    }

    let mut lz = 0.0;
    for (m, kk) in (zi..zf).enumerate() {
        lz += temp_y[m] * lanczos_kernel(z - kk as f64, a);
    }

    <T as NumCast>::from(lz).unwrap()
}
