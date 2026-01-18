use ndarray::parallel::prelude::*;
use ndarray::prelude::*;
use numpy::{ndarray, PyArrayMethods, PyReadonlyArray3, PyReadwriteArray2, ToPyArray};
use pyo3::prelude::*;
use rayon::prelude::*;

#[pyfunction]
pub fn lmip(
    image: PyReadonlyArray3<i16>,
    axis: usize,
    tmin: i16,
    tmax: i16,
    mut out: PyReadwriteArray2<i16>,
) -> PyResult<()> {
    let image_arr = image.as_array();
    let mut out_arr = out.as_array_mut();
    let dims = image_arr.shape();
    let (sz, sy, sx) = (dims[0], dims[1], dims[2]);

    match axis {
        0 => {
            // AXIAL
            for x in 0..sx {
                for y in 0..sy {
                    let mut max_val = image_arr[[0, y, x]];
                    let mut start = max_val >= tmin && max_val <= tmax;
                    for z in 0..sz {
                        let val = image_arr[[z, y, x]];
                        if val > max_val {
                            max_val = val;
                        } else if val < max_val && start {
                            break;
                        }
                        if val >= tmin && val <= tmax {
                            start = true;
                        }
                    }
                    out_arr[[y, x]] = max_val;
                }
            }
        }
        1 => {
            // CORONAL
            for z in 0..sz {
                for x in 0..sx {
                    let mut max_val = image_arr[[z, 0, x]];
                    let mut start = max_val >= tmin && max_val <= tmax;
                    for y in 0..sy {
                        let val = image_arr[[z, y, x]];
                        if val > max_val {
                            max_val = val;
                        } else if val < max_val && start {
                            break;
                        }
                        if val >= tmin && val <= tmax {
                            start = true;
                        }
                    }
                    out_arr[[z, x]] = max_val;
                }
            }
        }
        2 => {
            // SAGITTAL
            for z in 0..sz {
                for y in 0..sy {
                    let mut max_val = image_arr[[z, y, 0]];
                    let mut start = max_val >= tmin && max_val <= tmax;
                    for x in 0..sx {
                        let val = image_arr[[z, y, x]];
                        if val > max_val {
                            max_val = val;
                        } else if val < max_val && start {
                            break;
                        }
                        if val >= tmin && val <= tmax {
                            start = true;
                        }
                    }
                    out_arr[[z, y]] = max_val;
                }
            }
        }
        _ => (),
    }

    Ok(())
}

#[inline(always)]
fn get_opacity(vl: i16, wl: i16, ww: i16) -> f32 {
    let min_value = wl - (ww / 2);
    let max_value = wl + (ww / 2);

    if vl < min_value {
        0.0
    } else if vl > max_value {
        1.0
    } else {
        (vl - min_value) as f32 / (max_value - min_value) as f32
    }
}

#[pyfunction]
pub fn mida_old(
    image: PyReadonlyArray3<i16>,
    axis: usize,
    wl: i16,
    ww: i16,
    mut out: PyReadwriteArray2<i16>,
) -> PyResult<()> {
    let image_arr = image.as_array();
    let mut out_arr = out.as_array_mut();
    let dims = image_arr.shape();
    let (sz, sy, sx) = (dims[0], dims[1], dims[2]);

    let min = *image_arr.iter().min().unwrap_or(&0);
    let max = *image_arr.iter().max().unwrap_or(&0);
    let range = (max - min) as f32;

    match axis {
        0 => {
            // AXIAL
            let out_ptr = out_arr.as_mut_ptr() as usize;
            let out_strides = out_arr.strides();
            (0..sx).into_par_iter().for_each(|x| {
                for y in 0..sy {
                    let mut fmax = 0.0f32;
                    let mut alpha_p = 0.0f32;
                    let mut colour_p = 0.0f32;

                    for z in 0..sz {
                        let vl = image_arr[[z, y, x]];
                        let fpi = (vl - min) as f32 / range;

                        let dl = if fpi > fmax {
                            let temp = fpi - fmax;
                            fmax = fpi;
                            temp
                        } else {
                            0.0
                        };

                        let bt = 1.0 - dl;
                        let colour = fpi;
                        let alpha = get_opacity(vl as i16, wl, ww);

                        let new_colour = (bt * colour_p) + (1.0 - bt * alpha_p) * colour * alpha;
                        let new_alpha = (bt * alpha_p) + (1.0 - bt * alpha_p) * alpha;

                        colour_p = new_colour;
                        alpha_p = new_alpha;

                        if alpha_p >= 1.0 {
                            break;
                        }
                    }
                    unsafe {
                        let ptr = out_ptr as *mut i16;
                        let offset = y as isize * out_strides[0] + x as isize * out_strides[1];
                        *ptr.offset(offset) = (range * colour_p + min as f32) as i16;
                    }
                }
            });
        }
        1 => {
            // CORONAL
            let out_ptr = out_arr.as_mut_ptr() as usize;
            let out_strides = out_arr.strides();
            (0..sz).into_par_iter().for_each(|z| {
                for x in 0..sx {
                    let mut fmax = 0.0f32;
                    let mut alpha_p = 0.0f32;
                    let mut colour_p = 0.0f32;

                    for y in 0..sy {
                        let vl = image_arr[[z, y, x]];
                        let fpi = (vl - min) as f32 / range;

                        let dl = if fpi > fmax {
                            let temp = fpi - fmax;
                            fmax = fpi;
                            temp
                        } else {
                            0.0
                        };

                        let bt = 1.0 - dl;
                        let colour = fpi;
                        let alpha = get_opacity(vl, wl, ww);

                        let new_colour = (bt * colour_p) + (1.0 - bt * alpha_p) * colour * alpha;
                        let new_alpha = (bt * alpha_p) + (1.0 - bt * alpha_p) * alpha;

                        colour_p = new_colour;
                        alpha_p = new_alpha;

                        if alpha_p >= 1.0 {
                            break;
                        }
                    }
                    unsafe {
                        let ptr = out_ptr as *mut i16;
                        let offset = z as isize * out_strides[0] + x as isize * out_strides[1];
                        *ptr.offset(offset) = (range * colour_p + min as f32) as i16;
                    }
                }
            });
        }
        2 => {
            // SAGITTAL
            let out_ptr = out_arr.as_mut_ptr() as usize;
            let out_strides = out_arr.strides();
            (0..sz).into_par_iter().for_each(|z| {
                for y in 0..sy {
                    let mut fmax = 0.0f32;
                    let mut alpha_p = 0.0f32;
                    let mut colour_p = 0.0f32;

                    for x in 0..sx {
                        let vl = image_arr[[z, y, x]];
                        let fpi = (vl - min) as f32 / range;

                        let dl = if fpi > fmax {
                            let temp = fpi - fmax;
                            fmax = fpi;
                            temp
                        } else {
                            0.0
                        };

                        let bt = 1.0 - dl;
                        let colour = fpi;
                        let alpha = get_opacity(vl, wl, ww);

                        let new_colour = (bt * colour_p) + (1.0 - bt * alpha_p) * colour * alpha;
                        let new_alpha = (bt * alpha_p) + (1.0 - bt * alpha_p) * alpha;

                        colour_p = new_colour;
                        alpha_p = new_alpha;

                        if alpha_p >= 1.0 {
                            break;
                        }
                    }
                    unsafe {
                        let ptr = out_ptr as *mut i16;
                        let offset = z as isize * out_strides[0] + y as isize * out_strides[1];
                        *ptr.offset(offset) = (range * colour_p + min as f32) as i16;
                    }
                }
            });
        }
        _ => (),
    }
    Ok(())
}

#[pyfunction]
pub fn mida(
    image: PyReadonlyArray3<i16>,
    axis: usize,
    wl: i16,
    ww: i16,
    mut out: PyReadwriteArray2<i16>,
) {
    let img = image.as_array();
    let mut out_view = out.as_array_mut();

    // Cálculos preliminares
    let img_min = *img.iter().min().unwrap_or(&0) as f32;
    let img_max = *img.iter().max().unwrap_or(&0) as f32;
    let range = img_max - img_min;

    par_azip!((index (r, c), val in &mut out_view) {
        // Para cada pixel (r, c) na saída, calculamos o raio
        // Selecionamos a linha de pixels através do volume
        let lane = match axis {
            0 => img.slice(s![.., r, c]), // Z é o que sobra
            1 => img.slice(s![r, .., c]), // Y é o que sobra
            _ => img.slice(s![r, c, ..]), // X é o que sobra
        };

        let mut fmax = 0.0;
        let mut alpha_p = 0.0;
        let mut colour_p = 0.0;
        let mut final_colour = 0.0;

        for &vl_raw in lane {
            let vl = vl_raw as f32;
            let fpi = (1.0 / range) * (vl - img_min);

            let dl = if fpi > fmax {
                let diff = fpi - fmax;
                fmax = fpi;
                diff
            } else {
                0.0
            };

            let bt = 1.0 - dl;
            let alpha = get_opacity(vl_raw, wl, ww);

            let colour = (bt * colour_p) + (1.0 - bt * alpha_p) * fpi * alpha;
            let current_alpha = (bt * alpha_p) + (1.0 - bt * alpha_p) * alpha;

            colour_p = colour;
            alpha_p = current_alpha;
            final_colour = colour;

            if current_alpha >= 1.0 {
                break;
            }
        }

        *val = (range * final_colour + img_min) as i16;
    });
}

#[inline(always)]
fn finite_difference(
    image: &ndarray::ArrayView3<i16>,
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

    let gx = (image[[z, y, fx]] - image[[z, y, px]]) as f32 / (2.0 * h);
    let gy = (image[[z, fy, x]] - image[[z, py, x]]) as f32 / (2.0 * h);
    let gz = (image[[fz, y, x]] - image[[pz, y, x]]) as f32 / (2.0 * h);

    [gx, gy, gz]
}

fn calc_fcm_intensity(
    image: &ndarray::ArrayView3<i16>,
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

#[pyfunction]
pub fn fast_countour_mip(
    py: Python,
    image: PyReadonlyArray3<i16>,
    n: f32,
    axis: usize,
    wl: i16,
    ww: i16,
    tmip: usize,
    mut out: PyReadwriteArray2<i16>,
) -> PyResult<()> {
    let image_arr = image.as_array();
    let dims = image_arr.shape();
    let (sz, sy, sx) = (dims[0], dims[1], dims[2]);

    let mut dir = [0.0f32, 0.0, 0.0];
    match axis {
        0 => dir[2] = 1.0,
        1 => dir[1] = 1.0,
        2 => dir[0] = 1.0,
        _ => (),
    }

    // Calculate FCM intensity for entire volume
    let mut tmp = ndarray::Array3::<i16>::zeros((sz, sy, sx));

    par_azip!((index (z, y, x), val in &mut tmp){
        *val = calc_fcm_intensity(&image_arr, x, y, z, n, &dir) as i16;
    });

    let tmp_py = tmp.to_pyarray(py);

    match tmip {
        0 => {
            // MIP - Maximum Intensity Projection
            // Similar ao arr.max(axis) do NumPy - calcula máximo ao longo do eixo especificado
            // Usa fold_axis que é o equivalente de alto nível do ndarray
            let max_result = tmp.fold_axis(Axis(axis), i16::MIN, |&a, &b| a.max(b));
            let mut out_arr = out.as_array_mut();
            out_arr.assign(&max_result);
        }
        1 => {
            // LMIP
            lmip(tmp_py.readonly(), axis, 700, 3033, out)?;
        }
        2 => {
            // MIDA
            mida(tmp_py.readonly(), axis, wl, ww, out);
        }
        _ => (),
    }

    Ok(())
}
