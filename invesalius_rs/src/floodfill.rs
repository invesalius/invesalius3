use ndarray::{ArrayView3, ArrayViewMut3};
use num_traits::NumCast;
use numpy::{PyReadonlyArray3, PyReadwriteArray3};
use pyo3::exceptions::PyTypeError;
use pyo3::prelude::*;
use std::collections::VecDeque;

use crate::types::{ImageTypes3, ImageTypesMut3, MaskTypesMut3};

pub fn floodfill_internal<T: PartialOrd + Copy, U: PartialOrd + Copy>(
    data: ArrayView3<T>,
    i: usize,
    j: usize,
    k: usize,
    v: T,
    fill: U,
    mut out: ArrayViewMut3<U>,
) {
    let dims = data.shape();
    let d = dims[0];
    let h = dims[1];
    let w = dims[2];

    let mut stack = VecDeque::new();
    stack.push_back((i, j, k));
    out[[k, j, i]] = fill;

    while let Some((x, y, z)) = stack.pop_front() {
        if z + 1 < d && data[[z + 1, y, x]] == v && out[[z + 1, y, x]] != fill {
            out[[z + 1, y, x]] = fill;
            stack.push_back((x, y, z + 1));
        }
        if z > 0 && data[[z - 1, y, x]] == v && out[[z - 1, y, x]] != fill {
            out[[z - 1, y, x]] = fill;
            stack.push_back((x, y, z - 1));
        }
        if y + 1 < h && data[[z, y + 1, x]] == v && out[[z, y + 1, x]] != fill {
            out[[z, y + 1, x]] = fill;
            stack.push_back((x, y + 1, z));
        }
        if y > 0 && data[[z, y - 1, x]] == v && out[[z, y - 1, x]] != fill {
            out[[z, y - 1, x]] = fill;
            stack.push_back((x, y - 1, z));
        }
        if x + 1 < w && data[[z, y, x + 1]] == v && out[[z, y, x + 1]] != fill {
            out[[z, y, x + 1]] = fill;
            stack.push_back((x + 1, y, z));
        }
        if x > 0 && data[[z, y, x - 1]] == v && out[[z, y, x - 1]] != fill {
            out[[z, y, x - 1]] = fill;
            stack.push_back((x - 1, y, z));
        }
    }
}

pub fn generic_floodfill_threshold<T: PartialOrd + Copy>(
    data_arr: ArrayView3<T>,
    seeds: Vec<(usize, usize, usize)>,
    t0: T,
    t1: T,
    fill: u8,
    strct: PyReadonlyArray3<u8>,
    mut out: PyReadwriteArray3<u8>,
) {
    let strct_arr = strct.as_array();
    let mut out_arr = out.as_array_mut();

    let data_dims = data_arr.shape();
    let dz = data_dims[0];
    let dy = data_dims[1];
    let dx = data_dims[2];

    let strct_dims = strct_arr.shape();
    let odz = strct_dims[0];
    let ody = strct_dims[1];
    let odx = strct_dims[2];

    let offset_z = odz / 2;
    let offset_y = ody / 2;
    let offset_x = odx / 2;

    let mut stack = VecDeque::new();

    for (i, j, k) in seeds {
        let val = data_arr[[k, j, i]];
        if val >= t0 && val <= t1 {
            stack.push_back((i, j, k));
            out_arr[[k, j, i]] = fill;
        }
    }

    while let Some((x, y, z)) = stack.pop_back() {
        out_arr[[z, y, x]] = fill;

        for kk in 0..odz {
            let zo = z as isize + kk as isize - offset_z as isize;
            if zo < 0 || zo >= dz as isize {
                continue;
            }
            let zo = zo as usize;

            for jj in 0..ody {
                let yo = y as isize + jj as isize - offset_y as isize;
                if yo < 0 || yo >= dy as isize {
                    continue;
                }
                let yo = yo as usize;

                for ii in 0..odx {
                    if strct_arr[[kk, jj, ii]] != 0 {
                        let xo = x as isize + ii as isize - offset_x as isize;
                        if xo < 0 || xo >= dx as isize {
                            continue;
                        }
                        let xo = xo as usize;

                        if out_arr[[zo, yo, xo]] != fill {
                            let val = data_arr[[zo, yo, xo]];
                            if val >= t0 && val <= t1 {
                                out_arr[[zo, yo, xo]] = fill;
                                stack.push_back((xo, yo, zo));
                            }
                        }
                    }
                }
            }
        }
    }
}

pub fn generic_floodfill_threshold_inplace<T: PartialOrd + Copy>(
    mut data: ArrayViewMut3<T>,
    seeds: Vec<(usize, usize, usize)>,
    t0: T,
    t1: T,
    fill: T,
    strct: PyReadonlyArray3<u8>,
) {
    let strct_arr = strct.as_array();

    let data_dims = data.shape();
    let dz = data_dims[0];
    let dy = data_dims[1];
    let dx = data_dims[2];

    let strct_dims = strct_arr.shape();
    let odz = strct_dims[0];
    let ody = strct_dims[1];
    let odx = strct_dims[2];

    let offset_z = odz / 2;
    let offset_y = ody / 2;
    let offset_x = odx / 2;

    let mut stack = VecDeque::new();

    for (i, j, k) in seeds {
        let val = data[[k, j, i]];
        if val >= t0 && val <= t1 {
            stack.push_back((i, j, k));
            data[[k, j, i]] = fill;
        }
    }

    while let Some((x, y, z)) = stack.pop_back() {
        data[[z, y, x]] = fill;

        for kk in 0..odz {
            let zo = z as isize + kk as isize - offset_z as isize;
            if zo < 0 || zo >= dz as isize {
                continue;
            }
            let zo = zo as usize;

            for jj in 0..ody {
                let yo = y as isize + jj as isize - offset_y as isize;
                if yo < 0 || yo >= dy as isize {
                    continue;
                }
                let yo = yo as usize;

                for ii in 0..odx {
                    if strct_arr[[kk, jj, ii]] != 0 {
                        let xo = x as isize + ii as isize - offset_x as isize;
                        if xo < 0 || xo >= dx as isize {
                            continue;
                        }
                        let xo = xo as usize;

                        if data[[zo, yo, xo]] != fill {
                            let val = data[[zo, yo, xo]];
                            if val >= t0 && val <= t1 {
                                data[[zo, yo, xo]] = fill;
                                stack.push_back((xo, yo, zo));
                            }
                        }
                    }
                }
            }
        }
    }
}

#[pyfunction]
pub fn floodfill_auto_threshold(
    data: PyReadonlyArray3<i16>,
    seeds: Vec<(usize, usize, usize)>,
    p: f32,
    fill: u8,
    mut out: PyReadwriteArray3<u8>,
) -> PyResult<()> {
    let data_arr = data.as_array();
    let mut out_arr = out.as_array_mut();

    let dims = data_arr.shape();
    let d = dims[0];
    let h = dims[1];
    let w = dims[2];

    let mut stack = VecDeque::new();

    for (i, j, k) in seeds {
        stack.push_back((i, j, k));
        out_arr[[k, j, i]] = fill;
    }

    while let Some((x, y, z)) = stack.pop_front() {
        let val = data_arr[[z, y, x]] as f32;
        let t0 = (val * (1.0 - p)).ceil() as i16;
        let t1 = (val * (1.0 + p)).floor() as i16;

        if z + 1 < d && out_arr[[z + 1, y, x]] != fill {
            let next_val = data_arr[[z + 1, y, x]];
            if next_val >= t0 && next_val <= t1 {
                out_arr[[z + 1, y, x]] = fill;
                stack.push_back((x, y, z + 1));
            }
        }
        if z > 0 && out_arr[[z - 1, y, x]] != fill {
            let next_val = data_arr[[z - 1, y, x]];
            if next_val >= t0 && next_val <= t1 {
                out_arr[[z - 1, y, x]] = fill;
                stack.push_back((x, y, z - 1));
            }
        }
        if y + 1 < h && out_arr[[z, y + 1, x]] != fill {
            let next_val = data_arr[[z, y + 1, x]];
            if next_val >= t0 && next_val <= t1 {
                out_arr[[z, y + 1, x]] = fill;
                stack.push_back((x, y + 1, z));
            }
        }
        if y > 0 && out_arr[[z, y - 1, x]] != fill {
            let next_val = data_arr[[z, y - 1, x]];
            if next_val >= t0 && next_val <= t1 {
                out_arr[[z, y - 1, x]] = fill;
                stack.push_back((x, y - 1, z));
            }
        }
        if x + 1 < w && out_arr[[z, y, x + 1]] != fill {
            let next_val = data_arr[[z, y, x + 1]];
            if next_val >= t0 && next_val <= t1 {
                out_arr[[z, y, x + 1]] = fill;
                stack.push_back((x + 1, y, z));
            }
        }
        if x > 0 && out_arr[[z, y, x - 1]] != fill {
            let next_val = data_arr[[z, y, x - 1]];
            if next_val >= t0 && next_val <= t1 {
                out_arr[[z, y, x - 1]] = fill;
                stack.push_back((x - 1, y, z));
            }
        }
    }

    Ok(())
}

#[pyfunction]
pub fn floodfill<'py>(
    data: ImageTypes3<'py>,
    i: usize,
    j: usize,
    k: usize,
    v: Bound<'py, PyAny>,
    fill: Bound<'py, PyAny>,
    out: MaskTypesMut3<'py>,
) -> PyResult<()> {
    match (data, out) {
        (ImageTypes3::I16(data), MaskTypesMut3::U8(mut out)) => {
            floodfill_internal(
                data.as_array(),
                i,
                j,
                k,
                v.extract::<i16>()?,
                fill.extract::<u8>()?,
                out.as_array_mut(),
            );
            Ok(())
        }
        (ImageTypes3::U8(data), MaskTypesMut3::U8(mut out)) => {
            floodfill_internal(
                data.as_array(),
                i,
                j,
                k,
                v.extract::<u8>()?,
                fill.extract::<u8>()?,
                out.as_array_mut(),
            );
            Ok(())
        }
        (ImageTypes3::F64(data), MaskTypesMut3::U8(mut out)) => {
            floodfill_internal(
                data.as_array(),
                i,
                j,
                k,
                v.extract::<f64>()?,
                fill.extract::<u8>()?,
                out.as_array_mut(),
            );
            Ok(())
        }
    }
}

pub fn fill_holes_automatically_internal<U: PartialOrd + Copy + NumCast>(
    mut mask: ArrayViewMut3<U>,
    labels: PyReadonlyArray3<u16>,
    nlabels: u32,
    max_size: u32,
) -> bool {
    let labels_arr = labels.as_array();

    let mut sizes = vec![0u32; (nlabels + 1) as usize];

    for &label in labels_arr.iter() {
        sizes[label as usize] += 1;
    }

    let mut modified = false;
    for &size in &sizes {
        if size > 0 && size <= max_size {
            modified = true;
            break;
        }
    }

    if !modified {
        return false;
    }

    let mask_dims = mask.shape();
    let dz = mask_dims[0];
    let dy = mask_dims[1];
    let dx = mask_dims[2];

    for z in 0..dz {
        for y in 0..dy {
            for x in 0..dx {
                let label = labels_arr[[z, y, x]];
                if sizes[label as usize] <= max_size {
                    mask[[z, y, x]] = NumCast::from(254).unwrap_or(mask[[z, y, x]]);
                }
            }
        }
    }

    true
}

#[pyfunction]
pub fn floodfill_threshold<'py>(
    data: ImageTypes3<'py>,
    seeds: Vec<(usize, usize, usize)>,
    t0: Bound<'py, PyAny>,
    t1: Bound<'py, PyAny>,
    fill: u8,
    strct: PyReadonlyArray3<u8>,
    out: PyReadwriteArray3<u8>,
) -> PyResult<()> {
    match data {
        ImageTypes3::I16(data) => {
            generic_floodfill_threshold(
                data.as_array(),
                seeds,
                t0.extract::<i16>()?,
                t1.extract::<i16>()?,
                fill,
                strct,
                out,
            );
            Ok(())
        }
        ImageTypes3::U8(data) => {
            generic_floodfill_threshold(
                data.as_array(),
                seeds,
                t0.extract::<u8>()?,
                t1.extract::<u8>()?,
                fill,
                strct,
                out,
            );
            Ok(())
        }
        ImageTypes3::F64(data) => {
            generic_floodfill_threshold(
                data.as_array(),
                seeds,
                t0.extract::<f64>()?,
                t1.extract::<f64>()?,
                fill,
                strct,
                out,
            );
            Ok(())
        }
    }
}

#[pyfunction]
pub fn floodfill_threshold_inplace<'py>(
    data: ImageTypesMut3<'py>,
    seeds: Vec<(usize, usize, usize)>,
    t0: Bound<'py, PyAny>,
    t1: Bound<'py, PyAny>,
    fill: Bound<'py, PyAny>,
    strct: PyReadonlyArray3<u8>,
) -> PyResult<()> {
    match data {
        ImageTypesMut3::I16(mut data) => {
            generic_floodfill_threshold_inplace(
                data.as_array_mut(),
                seeds,
                t0.extract::<i16>()?,
                t1.extract::<i16>()?,
                fill.extract::<i16>()?,
                strct,
            );
            Ok(())
        }
        ImageTypesMut3::U8(mut data) => {
            generic_floodfill_threshold_inplace(
                data.as_array_mut(),
                seeds,
                t0.extract::<u8>()?,
                t1.extract::<u8>()?,
                fill.extract::<u8>()?,
                strct,
            );
            Ok(())
        }
        ImageTypesMut3::F64(mut data) => {
            generic_floodfill_threshold_inplace(
                data.as_array_mut(),
                seeds,
                t0.extract::<f64>()?,
                t1.extract::<f64>()?,
                fill.extract::<f64>()?,
                strct,
            );
            Ok(())
        }
    }
}

#[pyfunction]
pub fn fill_holes_automatically<'py>(
    mask: MaskTypesMut3<'py>,
    labels: PyReadonlyArray3<u16>,
    nlabels: u32,
    max_size: u32,
) -> PyResult<bool> {
    match mask {
        MaskTypesMut3::U8(mut mask) => Ok(fill_holes_automatically_internal(
            mask.as_array_mut(),
            labels,
            nlabels,
            max_size,
        )),
        _ => Err(PyTypeError::new_err("Invalid mask type")),
    }
}
