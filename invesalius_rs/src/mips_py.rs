use ndarray::parallel::prelude::*;
use numpy::{PyReadonlyArray3, PyReadwriteArray2};
use pyo3::exceptions::PyTypeError;
use pyo3::prelude::*;

use crate::mips::{fast_countour_mip_internal, get_opacity, mida_internal};
use crate::types::{ImageTypes3, ImageTypesMut2, MaskTypesMut2};

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
                        let alpha = get_opacity(vl as f32, wl as f32, ww as f32);

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
                        let alpha = get_opacity(vl as f32, wl as f32, ww as f32);

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
                        let alpha = get_opacity(vl as f32, wl as f32, ww as f32);

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
pub fn mida<'py>(
    image: ImageTypes3<'py>,
    axis: usize,
    wl: Bound<'py, PyAny>,
    ww: Bound<'py, PyAny>,
    out: MaskTypesMut2<'py>,
) -> PyResult<()> {
    match (image, out) {
        (ImageTypes3::I16(image), MaskTypesMut2::I16(mut out)) => {
            mida_internal(
                image.as_array(),
                axis,
                wl.extract::<i16>()?,
                ww.extract::<i16>()?,
                out.as_array_mut(),
            );
            Ok(())
        }
        (ImageTypes3::U8(image), MaskTypesMut2::U8(mut out)) => {
            mida_internal(
                image.as_array(),
                axis,
                wl.extract::<u8>()?,
                ww.extract::<u8>()?,
                out.as_array_mut(),
            );
            Ok(())
        }
        (ImageTypes3::F64(image), MaskTypesMut2::U8(mut out)) => {
            mida_internal(
                image.as_array(),
                axis,
                wl.extract::<f64>()?,
                ww.extract::<f64>()?,
                out.as_array_mut(),
            );
            Ok(())
        }
        _ => Err(PyTypeError::new_err("Invalid image or output type")),
    }
}

#[pyfunction]
pub fn fast_countour_mip<'py>(
    image: ImageTypes3<'py>,
    n: f32,
    axis: usize,
    wl: Bound<'py, PyAny>,
    ww: Bound<'py, PyAny>,
    tmip: usize,
    out: ImageTypesMut2<'py>,
) -> PyResult<()> {
    match (image, out) {
        (ImageTypes3::I16(image), ImageTypesMut2::I16(mut out)) => {
            fast_countour_mip_internal(
                image.as_array(),
                n,
                axis,
                wl.extract::<i16>()?,
                ww.extract::<i16>()?,
                tmip,
                out.as_array_mut(),
            );
            Ok(())
        }
        (ImageTypes3::U8(image), ImageTypesMut2::U8(mut out)) => {
            fast_countour_mip_internal(
                image.as_array(),
                n,
                axis,
                wl.extract::<u8>()?,
                ww.extract::<u8>()?,
                tmip,
                out.as_array_mut(),
            );
            Ok(())
        }
        (ImageTypes3::F64(image), ImageTypesMut2::F64(mut out)) => {
            fast_countour_mip_internal(
                image.as_array(),
                n,
                axis,
                wl.extract::<f64>()?,
                ww.extract::<f64>()?,
                tmip,
                out.as_array_mut(),
            );
            Ok(())
        }
        _ => Err(PyTypeError::new_err("Invalid image or output type")),
    }
}
