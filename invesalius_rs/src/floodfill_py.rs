use numpy::{PyReadonlyArray2, PyReadonlyArray3, PyReadwriteArray3};
use pyo3::exceptions::PyTypeError;
use pyo3::prelude::*;
use std::collections::VecDeque;

use crate::floodfill::{
    fill_holes_automatically_internal, floodfill_internal, generic_floodfill_threshold,
    generic_floodfill_threshold_inplace, floodfill_voronoi_inplace_internal, jump_flooding_internal,
};
use crate::types::{ImageTypes3, ImageTypesMut3, MaskTypesMut3};

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

#[pyfunction]
pub fn floodfill_threshold<'py>(
    data: ImageTypes3<'py>,
    seeds: Vec<(usize, usize, usize)>,
    t0: Bound<'py, PyAny>,
    t1: Bound<'py, PyAny>,
    fill: u8,
    strct: PyReadonlyArray3<u8>,
    out: MaskTypesMut3<'py>,
) -> PyResult<()> {
    match (data, out) {
        (ImageTypes3::I16(data), MaskTypesMut3::U8(mut out)) => {
            generic_floodfill_threshold(
                data.as_array(),
                seeds,
                t0.extract::<i16>()?,
                t1.extract::<i16>()?,
                fill,
                strct.as_array(),
                out.as_array_mut(),
            );
            Ok(())
        }
        (ImageTypes3::U8(data), MaskTypesMut3::U8(mut out)) => {
            generic_floodfill_threshold(
                data.as_array(),
                seeds,
                t0.extract::<u8>()?,
                t1.extract::<u8>()?,
                fill,
                strct.as_array(),
                out.as_array_mut(),
            );
            Ok(())
        }
        (ImageTypes3::F64(data), MaskTypesMut3::U8(mut out)) => {
            generic_floodfill_threshold(
                data.as_array(),
                seeds,
                t0.extract::<f64>()?,
                t1.extract::<f64>()?,
                fill,
                strct.as_array(),
                out.as_array_mut(),
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
                strct.as_array(),
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
                strct.as_array(),
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
                strct.as_array(),
            );
            Ok(())
        }
    }
}

#[pyfunction]
pub fn fill_holes_automatically<'py>(
    mask: MaskTypesMut3<'py>,
    labels: PyReadonlyArray3<u32>,
    nlabels: u32,
    max_size: u32,
) -> PyResult<bool> {
    match mask {
        MaskTypesMut3::U8(mut mask) => Ok(fill_holes_automatically_internal(
            mask.as_array_mut(),
            labels.as_array(),
            nlabels,
            max_size,
        )),
        _ => Err(PyTypeError::new_err("Invalid mask type")),
    }
}

#[pyfunction]
pub fn floodfill_voronoi_inplace<'py>(
    mut data: PyReadwriteArray3<f32>,
    seeds: Vec<(usize, usize, usize)>,
    strct: PyReadonlyArray3<u8>,
    distance_fn: u8,
) -> PyResult<()> {
    floodfill_voronoi_inplace_internal(data.as_array_mut(), seeds, strct.as_array(), distance_fn);
    Ok(())
}

#[pyfunction]
pub fn jump_flooding(
    mut distance_map: PyReadwriteArray3<f32>,
    mut map_owners: PyReadwriteArray3<i32>,
    sites: PyReadonlyArray2<i32>,
    normalize: bool,
) -> PyResult<()> {
    jump_flooding_internal(
        distance_map.as_array_mut(),
        map_owners.as_array_mut(),
        sites.as_array(),
        normalize,
    );
    Ok(())
}