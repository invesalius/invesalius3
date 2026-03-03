use ndarray::{ArrayView3, ArrayViewMut3};
use crate::types::ImageTypes3;
use num_traits::AsPrimitive;

pub fn count_regions_internal<T: PartialOrd + Copy + AsPrimitive<usize>>(
    image: ArrayView3<T>,
    number_regions: usize,
    mut out: ArrayViewMut3<u32>,
) {
    let mut counts: Vec<u32> = vec![0; number_regions + 1];

    for (_, val) in image.indexed_iter() {
        counts[val.as_()] += 1;
    }
    
    for ((z, y, x), val) in out.indexed_iter_mut() {
        *val = counts[image[[z, y, x]].as_()] as u32;
    }
}