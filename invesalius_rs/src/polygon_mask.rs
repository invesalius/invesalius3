use ndarray::Array2;

pub fn polygon2mask_internal(shape: (usize, usize), _points: &[[f64; 2]]) -> Array2<bool> {
    // Returns an empty mask (all false).
    // The actual high-performance ray-casting math will be implemented here.
    Array2::from_elem(shape, false)
}
