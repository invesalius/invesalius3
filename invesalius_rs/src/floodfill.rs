use ndarray::{ArrayView3, ArrayViewMut3};
use numpy::{PyReadonlyArray3, PyReadwriteArray3};
use pyo3::prelude::*;
use std::collections::VecDeque;

use numpy::PyArrayMethods;
use crate::types::{SupportedArray, SupportedArrayMut};

#[pyfunction]
pub fn floodfill(
    data: PyReadonlyArray3<i16>,
    i: usize,
    j: usize,
    k: usize,
    v: i16,
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
    stack.push_back((i, j, k));
    out_arr[[k, j, i]] = fill;

    while let Some((x, y, z)) = stack.pop_front() {
        if z + 1 < d && data_arr[[z + 1, y, x]] == v && out_arr[[z + 1, y, x]] != fill {
            out_arr[[z + 1, y, x]] = fill;
            stack.push_back((x, y, z + 1));
        }
        if z > 0 && data_arr[[z - 1, y, x]] == v && out_arr[[z - 1, y, x]] != fill {
            out_arr[[z - 1, y, x]] = fill;
            stack.push_back((x, y, z - 1));
        }
        if y + 1 < h && data_arr[[z, y + 1, x]] == v && out_arr[[z, y + 1, x]] != fill {
            out_arr[[z, y + 1, x]] = fill;
            stack.push_back((x, y + 1, z));
        }
        if y > 0 && data_arr[[z, y - 1, x]] == v && out_arr[[z, y - 1, x]] != fill {
            out_arr[[z, y - 1, x]] = fill;
            stack.push_back((x, y - 1, z));
        }
        if x + 1 < w && data_arr[[z, y, x + 1]] == v && out_arr[[z, y, x + 1]] != fill {
            out_arr[[z, y, x + 1]] = fill;
            stack.push_back((x + 1, y, z));
        }
        if x > 0 && data_arr[[z, y, x - 1]] == v && out_arr[[z, y, x - 1]] != fill {
            out_arr[[z, y, x - 1]] = fill;
            stack.push_back((x - 1, y, z));
        }
    }

    Ok(())
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
pub fn fill_holes_automatically(
    mut mask: PyReadwriteArray3<u8>,
    labels: PyReadonlyArray3<u16>,
    nlabels: u32,
    max_size: u32,
) -> PyResult<bool> {
    let labels_arr = labels.as_array();
    let mut mask_arr = mask.as_array_mut();

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
        return Ok(false);
    }

    let mask_dims = mask_arr.shape();
    let dz = mask_dims[0];
    let dy = mask_dims[1];
    let dx = mask_dims[2];

    for z in 0..dz {
        for y in 0..dy {
            for x in 0..dx {
                let label = labels_arr[[z, y, x]];
                if sizes[label as usize] <= max_size {
                    mask_arr[[z, y, x]] = 254;
                }
            }
        }
    }

    Ok(true)
}

#[pyfunction]
pub fn floodfill_threshold<'py>(
    data: SupportedArray<'py>,
    seeds: Vec<(usize, usize, usize)>,
    t0: Bound<'py, PyAny>,
    t1: Bound<'py, PyAny>,
    fill: u8,
    strct: PyReadonlyArray3<u8>,
    out: PyReadwriteArray3<u8>,
) -> PyResult<()> {
    match data {
        SupportedArray::I16(data) => {
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
        SupportedArray::U8(data) => {
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
        SupportedArray::F64(data) => {
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
    data: SupportedArrayMut<'py>,
    seeds: Vec<(usize, usize, usize)>,
    t0: Bound<'py, PyAny>,
    t1: Bound<'py, PyAny>,
    fill: Bound<'py, PyAny>,
    strct: PyReadonlyArray3<u8>,
) -> PyResult<()> {
    match data {
        SupportedArrayMut::I16(mut data) => {
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
        SupportedArrayMut::U8(mut data) => {
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
        SupportedArrayMut::F64(mut data) => {
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
