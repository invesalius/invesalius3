use ndarray::{ArrayView3, ArrayViewMut3};
use num_traits::NumCast;
use std::collections::VecDeque;

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

pub fn fill_holes_automatically_internal<U: PartialOrd + Copy + NumCast>(
    mut mask: ArrayViewMut3<U>,
    labels: ArrayView3<u32>,
    nlabels: u32,
    max_size: u32,
) -> bool {
    let labels_arr = labels;

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

pub fn generic_floodfill_threshold<T: PartialOrd + Copy>(
    data: ArrayView3<T>,
    seeds: Vec<(usize, usize, usize)>,
    t0: T,
    t1: T,
    fill: u8,
    strct: ArrayView3<u8>,
    mut out: ArrayViewMut3<u8>,
) {
    let data_dims = data.shape();
    let dz = data_dims[0];
    let dy = data_dims[1];
    let dx = data_dims[2];

    let strct_dims = strct.shape();
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
            out[[k, j, i]] = fill;
        }
    }

    while let Some((x, y, z)) = stack.pop_back() {
        out[[z, y, x]] = fill;

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
                    if strct[[kk, jj, ii]] != 0 {
                        let xo = x as isize + ii as isize - offset_x as isize;
                        if xo < 0 || xo >= dx as isize {
                            continue;
                        }
                        let xo = xo as usize;

                        if out[[zo, yo, xo]] != fill {
                            let val = data[[zo, yo, xo]];
                            if val >= t0 && val <= t1 {
                                out[[zo, yo, xo]] = fill;
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
    mut data: ndarray::ArrayViewMut3<T>,
    seeds: Vec<(usize, usize, usize)>,
    t0: T,
    t1: T,
    fill: T,
    strct: ArrayView3<u8>,
) {
    let data_dims = data.shape();
    let dz = data_dims[0];
    let dy = data_dims[1];
    let dx = data_dims[2];

    let strct_dims = strct.shape();
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
                    if strct[[kk, jj, ii]] != 0 {
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
