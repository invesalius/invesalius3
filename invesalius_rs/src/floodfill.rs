use ndarray::{Array3, ArrayView2, ArrayView3, ArrayViewMut3, Zip};
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

pub fn floodfill_voronoi_inplace_internal(
    mut data: ArrayViewMut3<f32>,
    seeds: Vec<(usize, usize, usize)>,
    strct: ArrayView3<u8>,
    distance_fn: u8,
) {
    assert!(distance_fn == 0 || distance_fn == 1);

    let data_dims = data.shape();
    let dz = data_dims[0];
    let dy = data_dims[1];
    let dx = data_dims[2];

    let odz = strct.shape()[0];
    let ody = strct.shape()[1];
    let odx = strct.shape()[2];

    let offset_z = odz / 2;
    let offset_y = ody / 2;
    let offset_x = odx / 2;

    let mut stack = VecDeque::new();

    for (i, j, k) in seeds {
        stack.push_back((i, j, k, i, j, k));
        data[[k, j, i]] = 0.0;
    }

    while let Some((x, y, z, sx, sy, sz)) = stack.pop_back() {
        let mut dist: f32 = 0.0;
        if distance_fn == 0 {
            dist = ((x - sx) as f32) * ((x - sx) as f32)
                + ((y - sy) as f32) * ((y - sy) as f32)
                + ((z - sz) as f32) * ((z - sz) as f32);
        } else if distance_fn == 1 {
            dist = ((x - sx) as f32).abs() + ((y - sy) as f32).abs() + ((z - sz) as f32).abs();
        }
        if data[[z, y, x]] == -1.0 || data[[z, y, x]] < dist as f32 {
            data[[z, y, x]] = dist;
            for k in 0..odz {
                let zo = z + k - offset_z;
                for j in 0..ody {
                    let yo = y + j - offset_y;
                    for i in 0..odx {
                        let xo = x + i - offset_x;
                        if strct[[k, j, i]] != 0
                            && (0 <= xo && xo < dx)
                            && (0 <= yo && yo < dy)
                            && (0 <= zo && zo < dz)
                        {
                            stack.push_back((xo, yo, zo, sx, sy, sz));
                        }
                    }
                }
            }
        }
    }
}

pub fn jump_flooding_internal(
    mut distance_map: ArrayViewMut3<f32>,
    mut map_owners: ArrayViewMut3<i32>,
    sites: ArrayView2<i32>,
    normalize: bool,
) {
    let (size_z, size_y, size_x) = {
        let sh = distance_map.shape();
        (sh[0], sh[1], sh[2])
    };
    let number_sites = sites.shape()[0];

    if number_sites == 0 || size_x == 0 || size_y == 0 || size_z == 0 {
        return;
    }

    let mut owners_curr: Array3<i32> = map_owners.to_owned();
    let mut dist_curr: Array3<f32> = distance_map.to_owned();

    // Seed owners (1-based like the original cython code).
    for i in 0..number_sites {
        let z = sites[[i, 0]];
        let y = sites[[i, 1]];
        let x = sites[[i, 2]];

        if z < 0 || y < 0 || x < 0 {
            continue;
        }
        let (z, y, x) = (z as usize, y as usize, x as usize);
        if z >= size_z || y >= size_y || x >= size_x {
            continue;
        }

        owners_curr[[z, y, x]] = (i as i32) + 1;
        dist_curr[[z, y, x]] = 0.0;
    }

    let max_dim = size_x.max(size_y).max(size_z);
    let n_steps = if max_dim <= 1 {
        0usize
    } else {
        (usize::BITS as usize - 1) - (max_dim.leading_zeros() as usize)
    };

    let mut offset_x = size_x / 2;
    let mut offset_y = size_y / 2;
    let mut offset_z = size_z / 2;

    let mut owners_next: Array3<i32> = owners_curr.clone();
    let mut dist_next: Array3<f32> = dist_curr.clone();

    for _ in 0..n_steps {
        Zip::indexed(&mut dist_next)
            .and(&mut owners_next)
            .par_for_each(|(z, y, x), dist_out, owner_out| {
                let mut idx0 = owners_curr[[z, y, x]];
                let mut best_dist = dist_curr[[z, y, x]];

                for zi in -1i32..=1 {
                    for yi in -1i32..=1 {
                        for xi in -1i32..=1 {
                            if xi == 0 && yi == 0 && zi == 0 {
                                continue;
                            }

                            let sz = z as isize + (zi as isize) * (offset_z as isize);
                            let sy = y as isize + (yi as isize) * (offset_y as isize);
                            let sx = x as isize + (xi as isize) * (offset_x as isize);

                            if sz < 0
                                || sy < 0
                                || sx < 0
                                || sz >= size_z as isize
                                || sy >= size_y as isize
                                || sx >= size_x as isize
                            {
                                continue;
                            }

                            let idx1 = owners_curr[[sz as usize, sy as usize, sx as usize]];
                            if idx1 <= 0 {
                                continue;
                            }

                            let site_i = (idx1 - 1) as usize;
                            if site_i >= number_sites {
                                continue;
                            }

                            let z1 = sites[[site_i, 0]] as f32;
                            let y1 = sites[[site_i, 1]] as f32;
                            let x1 = sites[[site_i, 2]] as f32;

                            let dz = (z as f32) - z1;
                            let dy = (y as f32) - y1;
                            let dx = (x as f32) - x1;
                            let dist1 = (dz * dz + dy * dy + dx * dx).sqrt();

                            if idx0 > 0 {
                                if dist1 < best_dist {
                                    idx0 = idx1;
                                    best_dist = dist1;
                                }
                            } else {
                                idx0 = idx1;
                                best_dist = dist1;
                            }
                        }
                    }
                }

                *owner_out = idx0;
                *dist_out = best_dist;
            });

        std::mem::swap(&mut owners_curr, &mut owners_next);
        std::mem::swap(&mut dist_curr, &mut dist_next);

        offset_x /= 2;
        offset_y /= 2;
        offset_z /= 2;
    }

    if normalize {
        let mut counts = vec![0u32; number_sites];
        let mut sums = vec![[0i64; 3]; number_sites];

        for z in 0..size_z {
            for y in 0..size_y {
                for x in 0..size_x {
                    let owner = owners_curr[[z, y, x]];
                    if owner <= 0 {
                        continue;
                    }
                    let idx = (owner - 1) as usize;
                    if idx >= number_sites {
                        continue;
                    }

                    counts[idx] += 1;
                    sums[idx][0] += z as i64;
                    sums[idx][1] += y as i64;
                    sums[idx][2] += x as i64;
                }
            }
        }

        let mut new_sites = vec![[0i32; 3]; number_sites];
        for i in 0..number_sites {
            let c = counts[i] as i64;
            if c > 0 {
                new_sites[i][0] = (sums[i][0] / c) as i32;
                new_sites[i][1] = (sums[i][1] / c) as i32;
                new_sites[i][2] = (sums[i][2] / c) as i32;
            }
        }

        let mut max_dists = vec![0.0f32; number_sites];
        for z in 0..size_z {
            for y in 0..size_y {
                for x in 0..size_x {
                    let owner = owners_curr[[z, y, x]];
                    if owner <= 0 {
                        continue;
                    }
                    let idx = (owner - 1) as usize;
                    if idx >= number_sites {
                        continue;
                    }

                    let z0 = new_sites[idx][0] as f32;
                    let y0 = new_sites[idx][1] as f32;
                    let x0 = new_sites[idx][2] as f32;

                    let dz = (z as f32) - z0;
                    let dy = (y as f32) - y0;
                    let dx = (x as f32) - x0;
                    let d = (dz * dz + dy * dy + dx * dx).sqrt();

                    dist_curr[[z, y, x]] = d;
                    if d > max_dists[idx] {
                        max_dists[idx] = d;
                    }
                }
            }
        }

        for z in 0..size_z {
            for y in 0..size_y {
                for x in 0..size_x {
                    let owner = owners_curr[[z, y, x]];
                    if owner <= 0 {
                        continue;
                    }
                    let idx = (owner - 1) as usize;
                    if idx >= number_sites {
                        continue;
                    }
                    let max_d = max_dists[idx];
                    if max_d > 0.0 {
                        dist_curr[[z, y, x]] /= max_d;
                    }
                }
            }
        }
    }

    map_owners.assign(&owners_curr);
    distance_map.assign(&dist_curr);
}
