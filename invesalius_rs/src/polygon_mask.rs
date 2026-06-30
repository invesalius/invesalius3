use ndarray::Array2;
use rayon::prelude::*;

pub fn polygon2mask_internal(shape: (usize, usize), points: &[[f64; 2]]) -> Array2<bool> {
    let (w, h) = shape;
    
    // Handle empty polygons or zero-size images safely
    if points.is_empty() || w == 0 || h == 0 {
        return Array2::from_elem(shape, false);
    }
    
    // Optimization 1: Calculate Bounding Box
    let mut min_px = f64::MAX;
    let mut max_px = f64::MIN;
    let mut min_py = f64::MAX;
    let mut max_py = f64::MIN;
    
    for p in points {
        if p[0] < min_px { min_px = p[0]; }
        if p[0] > max_px { max_px = p[0]; }
        if p[1] < min_py { min_py = p[1]; }
        if p[1] > max_py { max_py = p[1]; }
    }
    
    // Safely clamp the bounding box to the screen dimensions (handles zooming off-screen)
    let min_x_idx = (min_px.floor() as isize - 1).max(0) as usize;
    let max_x_idx = (max_px.ceil() as isize + 1).max(0) as usize;
    let min_x_idx = min_x_idx.min(w);
    let max_x_idx = max_x_idx.min(w);
    
    let min_y_idx = (min_py.floor() as isize - 1).max(0) as usize;
    let max_y_idx = (max_py.ceil() as isize + 1).max(0) as usize;
    let min_y_idx = min_y_idx.min(h);
    let max_y_idx = max_y_idx.min(h);

    // Initialize flat vector for the mask
    let mut mask_vec = vec![false; w * h];
    
    // Optimization 2: Rayon Multithreading
    // We iterate over the rows in parallel (each chunk is one row of length h)
    mask_vec.par_chunks_exact_mut(h).enumerate().for_each(|(r, row)| {
        // Only process rows inside the X bounding box
        if r >= min_x_idx && r <= max_x_idx {
            let px = r as f64;
            let n = points.len();
            
            for (c, val) in row.iter_mut().enumerate() {
                // Only process columns inside the Y bounding box
                if c >= min_y_idx && c <= max_y_idx {
                    let py = c as f64;
                    let mut inside = false;
                    let mut j = n - 1;
                    
                    // Ray-Casting Algorithm
                    for i in 0..n {
                        let xi = points[i][0];
                        let yi = points[i][1];
                        let xj = points[j][0];
                        let yj = points[j][1];
                        
                        // Check if the horizontal ray from (px, py) to the right intersects edge i-j
                        // (yi > py) != (yj > py) guarantees we don't divide by zero when yi == yj
                        let intersect = ((yi > py) != (yj > py))
                            && (px < (xj - xi) * (py - yi) / (yj - yi) + xi);
                            
                        if intersect {
                            inside = !inside;
                        }
                        j = i;
                    }
                    *val = inside;
                }
            }
        }
    });
    
    // Convert back to 2D Array
    Array2::from_shape_vec((w, h), mask_vec).unwrap()
}
