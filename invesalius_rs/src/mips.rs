use ndarray::parallel::prelude::*;
use ndarray::prelude::*;
use num_traits::{Bounded, Num};
use num_traits::{NumCast, ToPrimitive};
use std::ops::Sub;

pub fn lmip<
    T: PartialOrd + Copy + ToPrimitive + Send + NumCast + Sync,
    U: PartialOrd + Copy + ToPrimitive + Send + NumCast + Sync,
>(
    image: ArrayView3<T>,
    axis: usize,
    tmin: T,
    tmax: T,
    mut out: ArrayViewMut2<U>,
) {
    let dims = image.shape();
    let (sz, sy, sx) = (dims[0], dims[1], dims[2]);

    match axis {
        0 => {
            // AXIAL
            for x in 0..sx {
                for y in 0..sy {
                    let mut max_val = image[[0, y, x]];
                    let mut start = max_val >= tmin && max_val <= tmax;
                    for z in 0..sz {
                        let val = image[[z, y, x]];
                        if val > max_val {
                            max_val = val;
                        } else if val < max_val && start {
                            break;
                        }
                        if val >= tmin && val <= tmax {
                            start = true;
                        }
                    }
                    out[[y, x]] = NumCast::from(max_val).unwrap();
                }
            }
        }
        1 => {
            // CORONAL
            for z in 0..sz {
                for x in 0..sx {
                    let mut max_val = image[[z, 0, x]];
                    let mut start = max_val >= tmin && max_val <= tmax;
                    for y in 0..sy {
                        let val = image[[z, y, x]];
                        if val > max_val {
                            max_val = val;
                        } else if val < max_val && start {
                            break;
                        }
                        if val >= tmin && val <= tmax {
                            start = true;
                        }
                    }
                    out[[z, x]] = NumCast::from(max_val).unwrap();
                }
            }
        }
        2 => {
            // SAGITTAL
            for z in 0..sz {
                for y in 0..sy {
                    let mut max_val = image[[z, y, 0]];
                    let mut start = max_val >= tmin && max_val <= tmax;
                    for x in 0..sx {
                        let val = image[[z, y, x]];
                        if val > max_val {
                            max_val = val;
                        } else if val < max_val && start {
                            break;
                        }
                        if val >= tmin && val <= tmax {
                            start = true;
                        }
                    }
                    out[[z, y]] = NumCast::from(max_val).unwrap();
                }
            }
        }
        _ => (),
    }
}

#[inline(always)]
pub(crate) fn get_opacity(vl: f32, wl: f32, ww: f32) -> f32 {
    let min_value = wl - (ww / 2.0);
    let max_value = wl + (ww / 2.0);

    if vl < min_value {
        0.0
    } else if vl > max_value {
        1.0
    } else {
        (vl - min_value) / (max_value - min_value)
    }
}

pub fn mida_internal<
    T: PartialOrd + Copy + ToPrimitive + Send + NumCast + Sync + Num,
    U: PartialOrd + Copy + ToPrimitive + Send + NumCast + Sync + Num,
>(
    image: ArrayView3<T>,
    axis: usize,
    wl: T,
    ww: T,
    mut out: ArrayViewMut2<U>,
) {
    // Preliminary calculations
    let img_min = image
        .iter()
        .map(|&x| <f32 as NumCast>::from(x).unwrap())
        .reduce(f32::min)
        .unwrap();
    let img_max = image
        .iter()
        .map(|&x| <f32 as NumCast>::from(x).unwrap())
        .reduce(f32::max)
        .unwrap();
    let range = img_max - img_min;

    par_azip!((index (r, c), val in &mut out) {
        // For each pixel (r, c) in the output, we calculate the ray
        // We select the line of pixels through the volume
        let lane = match axis {
            0 => image.slice(s![.., r, c]), // Z is what's left
            1 => image.slice(s![r, .., c]), // Y is what's left
            _ => image.slice(s![r, c, ..]), // X is what's left
        };

        let mut fmax = 0.0;
        let mut alpha_p = 0.0;
        let mut colour_p = 0.0;
        let mut final_colour = 0.0;

        for &vl_raw in lane {
            let vl = NumCast::from(vl_raw).unwrap();
            let fpi = (1.0 / range) * (vl - img_min);

            let dl = if fpi > fmax {
                let diff = fpi - fmax;
                fmax = fpi;
                diff
            } else {
                0.0
            };

            let bt = 1.0 - dl;
            let alpha = get_opacity(vl, <f32 as NumCast>::from(wl).unwrap(), <f32 as NumCast>::from(ww).unwrap());

            let colour = (bt * colour_p) + (1.0 - bt * alpha_p) * fpi * alpha;
            let current_alpha = (bt * alpha_p) + (1.0 - bt * alpha_p) * alpha;

            colour_p = colour;
            alpha_p = current_alpha;
            final_colour = colour;

            if current_alpha >= 1.0 {
                break;
            }
        }

        *val = NumCast::from(range * final_colour + img_min).unwrap();
    });
}

#[inline(always)]
fn finite_difference<
    T: PartialOrd + Copy + ToPrimitive + Send + NumCast + Sync + Sub<Output = T>,
>(
    image: ArrayView3<T>,
    x: usize,
    y: usize,
    z: usize,
    h: f32,
) -> [f32; 3] {
    let dims = image.shape();
    let (sz, sy, sx) = (dims[0], dims[1], dims[2]);

    let px = if x == 0 { 0 } else { x - 1 };
    let fx = if x == sx - 1 { sx - 1 } else { x + 1 };
    let py = if y == 0 { 0 } else { y - 1 };
    let fy = if y == sy - 1 { sy - 1 } else { y + 1 };
    let pz = if z == 0 { 0 } else { z - 1 };
    let fz = if z == sz - 1 { sz - 1 } else { z + 1 };

    let gx = (image[[z, y, fx]] - image[[z, y, px]]).to_f32().unwrap() / (2.0 * h);
    let gy = (image[[z, fy, x]] - image[[z, py, x]]).to_f32().unwrap() / (2.0 * h);
    let gz = (image[[fz, y, x]] - image[[pz, y, x]]).to_f32().unwrap() / (2.0 * h);

    [gx, gy, gz]
}

fn calc_fcm_intensity<T: PartialOrd + Copy + ToPrimitive + Send + NumCast + Sync + Num>(
    image: ArrayView3<T>,
    x: usize,
    y: usize,
    z: usize,
    n: f32,
    dir: &[f32; 3],
) -> f32 {
    let g = finite_difference(image, x, y, z, 1.0);
    let gm = (g[0] * g[0] + g[1] * g[1] + g[2] * g[2]).sqrt();
    if gm == 0.0 {
        return 0.0;
    }
    let d = g[0] * dir[0] + g[1] * dir[1] + g[2] * dir[2];
    let sf = (1.0 - (d / gm).abs()).powf(n);
    gm * sf
}

pub fn fast_countour_mip_internal<
    T: PartialOrd + Copy + ToPrimitive + Send + NumCast + Sync + Num + Bounded + PartialOrd,
>(
    image: ArrayView3<T>,
    n: f32,
    axis: usize,
    wl: T,
    ww: T,
    tmip: usize,
    mut out: ArrayViewMut2<T>,
) {
    let dims = image.shape();
    let (sz, sy, sx) = (dims[0], dims[1], dims[2]);

    let mut dir = [0.0f32, 0.0, 0.0];
    match axis {
        0 => dir[2] = 1.0,
        1 => dir[1] = 1.0,
        2 => dir[0] = 1.0,
        _ => (),
    }

    // Calculate FCM intensity for entire volume
    let mut tmp = Array3::<T>::zeros((sz, sy, sx));

    par_azip!((index (z, y, x), val in &mut tmp){
        *val = NumCast::from(calc_fcm_intensity(image, x, y, z, n, &dir)).unwrap();
    });

    match tmip {
        0 => {
            // MIP - Maximum Intensity Projection
            // Similar to NumPy's arr.max(axis) - calculates the maximum along the specified axis
            // Uses fold_axis which is the high-level equivalent in ndarray
            // let max_result = tmp.fold_axis(Axis(axis), <T as Sub>::Output::min_value().unwrap() as U, |&a, &b| a.max(b));
            let max_result = tmp.fold_axis(
                Axis(axis),
                <T as Bounded>::min_value(),
                |acc: &T, elt: &T| if *acc > *elt { *acc } else { *elt },
            );
            out.assign(&max_result);
        }
        1 => {
            // LMIP
            lmip(
                tmp.view(),
                axis,
                NumCast::from(700).unwrap(),
                NumCast::from(3033).unwrap(),
                out.view_mut(),
            );
        }
        2 => {
            // MIDA
            mida_internal(
                tmp.view(),
                axis,
                NumCast::from(wl).unwrap(),
                NumCast::from(ww).unwrap(),
                out,
            );
        }
        _ => (),
    }
}
