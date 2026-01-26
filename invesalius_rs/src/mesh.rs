use core::{f64, hash};
use nalgebra::{Point3, Vector3};
use ndarray::parallel::prelude::*;
use ndarray::{Array2, ArrayView2, ArrayViewMut2};
use num_traits::{AsPrimitive, NumCast};
use numpy::{ndarray, PyArrayMethods};
use pyo3::prelude::*;
use std::collections::{HashMap, HashSet, VecDeque};
use std::sync::Mutex;

use crate::types::{FaceArray, VertexArray};

trait Vertex: num_traits::Float + Copy + Send + Sync + NumCast + std::ops::AddAssign<Self> + AsPrimitive<f64> {}

impl Vertex for f32 {}
impl Vertex for f64 {}

trait Face: num_traits::PrimInt + Copy + Send + Sync + Ord + hash::Hash + AsPrimitive<usize> {}

impl Face for i32 {}
impl Face for i64 {}
impl Face for u32 {}
impl Face for u64 {}

pub fn context_aware_smoothing_internal<V, F, N>(
    vertices: ArrayViewMut2<V>,
    faces: ArrayViewMut2<F>,
    normals: ArrayViewMut2<N>,
    t: f64,
    tmax: f64,
    bmin: f64,
    n_iters: u32,
) where
    V: Vertex,
    F: Face,
    N: Vertex,
{
    let map_vface = build_map_vface(&faces.view());
    let edge_nfaces: HashMap<(F, F), i32> = HashMap::new();
    let border_vertices: HashSet<F> = HashSet::new();

    let stack_orientation = [0.0, 0.0, 1.0];
    let vertices_staircase = find_staircase_artifacts(
        &vertices.view(),
        &faces.view(),
        &normals.view(),
        &map_vface,
        stack_orientation,
        t,
    );
    let weights = calc_artifacts_weight(
        &vertices.view(),
        &faces.view(),
        &normals.view(),
        &map_vface,
        &vertices_staircase,
        tmax,
        bmin,
    );
    taubin_smooth(
        vertices,
        &faces.view(),
        &map_vface,
        &weights,
        0.5,
        -0.53,
        n_iters,
    );  
}

fn build_map_vface<F>(faces: &ArrayView2<F>) -> HashMap<usize, Vec<usize>>
where
    F: Face,
{
    let mut map_vface: HashMap<usize, Vec<usize>> = HashMap::new();
    for f_id in 0..faces.shape()[0] {
        let face = faces.row(f_id);
        for i in 0..face.len() {
            map_vface
                .entry(face[i].as_())
                .or_default()
                .push(f_id);
        }
    }
    map_vface
}

pub fn find_staircase_artifacts<V, F, N>(
    vertices: &ArrayView2<V>,
    _faces: &ArrayView2<F>,
    normals: &ArrayView2<N>,
    map_vface: &HashMap<usize, Vec<usize>>,
    stack_orientation: [f64; 3],
    t: f64,
) -> Vec<usize>
where
    V: Vertex,
    F: Face,
    N: Vertex,
{
    let n_vertices = vertices.shape()[0];
    let stack_orientation = Vector3::from_row_slice(&stack_orientation);

    let mut output = Vec::new();

    for v_id in 0..n_vertices {
        let mut max_z = f64::MIN;
        let mut min_z = f64::MAX;
        let mut max_y = f64::MIN;
        let mut min_y = f64::MAX;
        let mut max_x = f64::MIN;
        let mut min_x = f64::MAX;

        if let Some(f_ids) = map_vface.get(&v_id) {
            for &f_id in f_ids {
                let normal = normals.row(f_id);
                let normal_vec = Vector3::new(normal[0].as_(), normal[1].as_(), normal[2].as_());

                let of_z = 1.0 - (normal_vec.dot(&stack_orientation)).abs();
                let of_y = 1.0 - (normal_vec.dot(&Vector3::new(0.0, 1.0, 0.0))).abs();
                let of_x = 1.0 - (normal_vec.dot(&Vector3::new(1.0, 0.0, 0.0))).abs();

                if of_z > max_z {
                    max_z = of_z;
                }
                if of_z < min_z {
                    min_z = of_z;
                }
                if of_y > max_y {
                    max_y = of_y;
                }
                if of_y < min_y {
                    min_y = of_y;
                }
                if of_x > max_x {
                    max_x = of_x;
                }
                if of_x < min_x {
                    min_x = of_x;
                }

                if (max_z - min_z).abs() >= t
                    || (max_y - min_y).abs() >= t
                    || (max_x - min_x).abs() >= t
                {
                    output.push(v_id);
                    break;
                }
            }
        }
    }
    output
}

fn calc_artifacts_weight<V, F, N>(
    vertices: &ArrayView2<V>,
    faces: &ArrayView2<F>,
    _normals: &ArrayView2<N>,
    map_vface: &HashMap<usize, Vec<usize>>,
    vertices_staircase: &[usize],
    tmax: f64,
    bmin: f64,
) -> Vec<f64>
where
    V: Vertex,
    F: Face,
    N: Vertex,
{
    let n_vertices = vertices.shape()[0];
    let weights = Mutex::new(vec![bmin; n_vertices]);

    vertices_staircase.into_par_iter().for_each(|vi_id| {
        {
            let mut weights = weights.lock().unwrap();
            weights[*vi_id] = 1.0;
        }

        let near_vertices = get_near_vertices_to_v(
            &vertices,
            &faces,
            map_vface,
            *vi_id,
            tmax,
        );
        let vi = vertices.row(*vi_id);
        let p_vi = Point3::new(vi[0].as_(), vi[1].as_(), vi[2].as_());

        for &vj_id in &near_vertices {
            let vj = vertices.row(vj_id);
            let p_vj = Point3::new(vj[0].as_(), vj[1].as_(), vj[2].as_());
            let d = (p_vi - p_vj).norm();
            let value = (1.0 - d / tmax) * (1.0 - bmin) + bmin;

            {
                let mut weights = weights.lock().unwrap();
                if value > weights[vj_id] {
                    weights[vj_id] = value;
                }
            }
        }
    });

    weights.into_inner().unwrap()
}

fn calc_d<V, F>(
    vertices: &ArrayView2<V>,
    faces: &ArrayView2<F>,
    map_vface: &HashMap<usize, Vec<usize>>,
    v_id: usize,
) -> Vector3<f64>
where
    V: Vertex,
    F: Face,
{
    let vi = vertices.row(v_id);
    let p_vi = Vector3::new(vi[0].as_(), vi[1].as_(), vi[2].as_());

    let ring1 = get_ring1(faces, map_vface, v_id);
    let mut d = Vector3::zeros();
    let mut n = 0.0f64;

    if is_border(v_id) {
        for &vj_id in &ring1 {
            if is_border(vj_id) {
                let vj = vertices.row(vj_id);
                let p_vj = Vector3::new(vj[0].as_(), vj[1].as_(), vj[2].as_());
                d += p_vi - p_vj;
                n += 1.0;
            }
        }
    } else {
        for &vj_id in &ring1 {
            let vj = vertices.row(vj_id);
            let p_vj = Vector3::new(vj[0].as_(), vj[1].as_(), vj[2].as_());
            d += p_vi - p_vj;
            n += 1.0;
        }
    }

    if n > 0.0 {
        d / n
    } else {
        d
    }
}

fn is_border(_v_id: usize) -> bool {
    // Convert v_id to F type for lookup
    // Since we're using ArrayView, we need to check if the vertex index exists in border_vertices
    // For now, we'll need to convert: but border_vertices stores F, not usize
    // This is a design issue - border_vertices should probably be HashSet<usize>
    // For now, we'll check by converting back
    false // TODO: Fix this - border_vertices type mismatch
}

fn get_ring1<F>(
    faces: &ArrayView2<F>,
    map_vface: &HashMap<usize, Vec<usize>>,
    v_id: usize,
) -> HashSet<usize>
where
    F: Face,
{
    let mut ring1 = HashSet::new();
    if let Some(f_ids) = map_vface.get(&v_id) {
        for &f_id in f_ids {
            let face = faces.row(f_id);
            for i in 1..4 {
                let v = face[i].as_();
                if v != v_id {
                    ring1.insert(v);
                }
            }
        }
    }
    ring1
}

fn get_near_vertices_to_v<V, F>(
    vertices: &ArrayView2<V>,
    faces: &ArrayView2<F>,
    map_vface: &HashMap<usize, Vec<usize>>,
    v_id: usize,
    dmax: f64,
) -> Vec<usize>
where
    V: Vertex,
    F: Face,
{
    let mut near_vertices = Vec::new();
    let mut to_visit = VecDeque::new();
    let mut status_v = HashSet::new();

    let v_i = vertices.row(v_id);
    let p_i = Point3::new(v_i[0].as_(), v_i[1].as_(), v_i[2].as_());

    to_visit.push_back(v_id);
    status_v.insert(v_id);

    let dmax_sq = dmax * dmax;

    while let Some(current_v_id) = to_visit.pop_front() {
        if let Some(f_ids) = map_vface.get(&current_v_id) {
            for &f_id in f_ids {
                let face = faces.row(f_id);
                for i in 1..4 {
                    let v_j_id = face[i].as_();
                    if !status_v.contains(&v_j_id) {
                        status_v.insert(v_j_id);
                        let v_j = vertices.row(v_j_id);
                        let p_j = Point3::new(v_j[0].as_(), v_j[1].as_(), v_j[2].as_());
                        let dist_sq = (p_i - p_j).norm_squared();
                        if dist_sq <= dmax_sq {
                            near_vertices.push(v_j_id);
                            to_visit.push_back(v_j_id);
                        }
                    }
                }
            }
        }
    }
    near_vertices
}

fn taubin_smooth<V, F>(mut vertices: ArrayViewMut2<V>, faces: &ArrayView2<F>, map_vface: &HashMap<usize, Vec<usize>>, weights: &[f64], l: f64, m: f64, steps: u32)
where
    V: Vertex,
    F: Face,
{
    let n_vertices = vertices.shape()[0];
    let mut d_values: Array2<f64> = Array2::zeros((n_vertices, 3));

    for _ in 0..steps {
        // Calculate D for all vertices

        par_azip!((index i, mut d in d_values.outer_iter_mut()) {
            let d_vec = calc_d(&vertices.view(), faces, map_vface, i);
            d[0] = d_vec.x;
            d[1] = d_vec.y;
            d[2] = d_vec.z;
        });

        // Apply first smoothing step (lambda)
        par_azip!((index i, mut vertex in vertices.outer_iter_mut(), d in d_values.outer_iter()) {
            let dx: V = NumCast::from(weights[i] * l * d[0]).unwrap_or(vertex[0]);
            let dy: V = NumCast::from(weights[i] * l * d[1]).unwrap_or(vertex[1]);
            let dz: V = NumCast::from(weights[i] * l * d[2]).unwrap_or(vertex[2]);
            vertex[[0]] += dx;
            vertex[[1]] += dy;
            vertex[[2]] += dz;
        });

        par_azip!((index i, mut d in d_values.outer_iter_mut()) {
            let d_vec = calc_d(&vertices.view(), faces, map_vface, i);
            d[0] = d_vec.x;
            d[1] = d_vec.y;
            d[2] = d_vec.z;
        });


        // Apply second smoothing step (mu)
        par_azip!((index i, mut vertex in vertices.outer_iter_mut(), d in d_values.outer_iter()) {
            let dx: V = NumCast::from(weights[i] * m * d[0]).unwrap_or(vertex[0]);
            let dy: V = NumCast::from(weights[i] * m * d[1]).unwrap_or(vertex[1]);
            let dz: V = NumCast::from(weights[i] * m * d[2]).unwrap_or(vertex[2]);
            vertex[[0]] += dx;
            vertex[[1]] += dy;
            vertex[[2]] += dz;
        });
    }
}


#[pyfunction]   
pub fn context_aware_smoothing<'py>(
    vertices: VertexArray<'py>,
    faces: FaceArray<'py>,
    normals: VertexArray<'py>,
    t: f64,
    tmax: f64,
    bmin: f64,
    n_iters: u32,
) -> PyResult<()> {
    match (vertices, faces, normals) {
        // F32 vertices, I64 faces
        (VertexArray::F32(mut vertices), FaceArray::I64(mut faces), VertexArray::F32(mut normals)) => {
            println!("F32 vertices, I64 faces");
            context_aware_smoothing_internal(
                vertices.as_array_mut(),
                faces.as_array_mut(),
                normals.as_array_mut(),
                t,
                tmax,
                bmin,
                n_iters,
            );
            Ok(())
        }
        (VertexArray::F32(mut vertices), FaceArray::I64(mut faces), VertexArray::F64(mut normals)) => {
            println!("F32 vertices, I64 faces");
            context_aware_smoothing_internal(
                vertices.as_array_mut(),
                faces.as_array_mut(),
                normals.as_array_mut(),
                t,
                tmax,
                bmin,
                n_iters,
            );
            Ok(())
        }
        // F32 vertices, U64 faces
        (VertexArray::F32(mut vertices), FaceArray::U64(mut faces), VertexArray::F32(mut normals)) => {
            println!("F32 vertices, U64 faces");
            context_aware_smoothing_internal(
                vertices.as_array_mut(),
                faces.as_array_mut(),
                normals.as_array_mut(),
                t,
                tmax,
                bmin,
                n_iters,
            );
            Ok(())
        }
        (VertexArray::F32(mut vertices), FaceArray::U64(mut faces), VertexArray::F64(mut normals)) => {
            println!("F32 vertices, U64 faces");
            context_aware_smoothing_internal(
                vertices.as_array_mut(),
                faces.as_array_mut(),
                normals.as_array_mut(),
                t,
                tmax,
                bmin,
                n_iters,
            );
            Ok(())
        }
        // F32 vertices, I32 faces
        (VertexArray::F32(mut vertices), FaceArray::I32(mut faces), VertexArray::F32(mut normals)) => {
            println!("F32 vertices, I32 faces");
            context_aware_smoothing_internal(
                vertices.as_array_mut(),
                faces.as_array_mut(),
                normals.as_array_mut(),
                t,
                tmax,
                bmin,
                n_iters,
            );
            Ok(())
        }
        (VertexArray::F32(mut vertices), FaceArray::I32(mut faces), VertexArray::F64(mut normals)) => {
            println!("F32 vertices, I32 faces");
            context_aware_smoothing_internal(
                vertices.as_array_mut(),
                faces.as_array_mut(),
                normals.as_array_mut(),
                t,
                tmax,
                bmin,
                n_iters,
            );
            Ok(())
        }
        // F32 vertices, U32 faces
        (VertexArray::F32(mut vertices), FaceArray::U32(mut faces), VertexArray::F32(mut normals)) => {
            println!("F32 vertices, U32 faces");
            context_aware_smoothing_internal(
                vertices.as_array_mut(),
                faces.as_array_mut(),
                normals.as_array_mut(),
                t,
                tmax,
                bmin,
                n_iters,
            );
            Ok(())
        }
        (VertexArray::F32(mut vertices), FaceArray::U32(mut faces), VertexArray::F64(mut normals)) => {
            println!("F32 vertices, U32 faces");
            context_aware_smoothing_internal(
                vertices.as_array_mut(),
                faces.as_array_mut(),
                normals.as_array_mut(),
                t,
                tmax,
                bmin,
                n_iters,
            );
            Ok(())
        }
        // F64 vertices, I64 faces
        (VertexArray::F64(mut vertices), FaceArray::I64(mut faces), VertexArray::F32(mut normals)) => {
            println!("F64 vertices, I64 faces");
            context_aware_smoothing_internal(
                vertices.as_array_mut(),
                faces.as_array_mut(),
                normals.as_array_mut(),
                t,
                tmax,
                bmin,
                n_iters,
            );
            Ok(())
        }
        (VertexArray::F64(mut vertices), FaceArray::I64(mut faces), VertexArray::F64(mut normals)) => {
            println!("F64 vertices, I64 faces");
            context_aware_smoothing_internal(
                vertices.as_array_mut(),
                faces.as_array_mut(),
                normals.as_array_mut(),
                t,
                tmax,
                bmin,
                n_iters,
            );
            Ok(())
        }
        // F64 vertices, U64 faces
        (VertexArray::F64(mut vertices), FaceArray::U64(mut faces), VertexArray::F32(mut normals)) => {
            println!("F64 vertices, U64 faces");
            context_aware_smoothing_internal(
                vertices.as_array_mut(),
                faces.as_array_mut(),
                normals.as_array_mut(),
                t,
                tmax,
                bmin,
                n_iters,
            );
            Ok(())
        }
        (VertexArray::F64(mut vertices), FaceArray::U64(mut faces), VertexArray::F64(mut normals)) => {
            println!("F64 vertices, U64 faces");
                context_aware_smoothing_internal(
                vertices.as_array_mut(),
                faces.as_array_mut(),
                normals.as_array_mut(),
                t,
                tmax,
                bmin,
                n_iters,
            );
            Ok(())
        }
        // F64 vertices, I32 faces
        (VertexArray::F64(mut vertices), FaceArray::I32(mut faces), VertexArray::F32(mut normals)) => {
            println!("F64 vertices, I32 faces");
            context_aware_smoothing_internal(
                vertices.as_array_mut(),
                faces.as_array_mut(),
                normals.as_array_mut(),
                t,
                tmax,
                bmin,
                n_iters,
            );
            Ok(())
        }
        (VertexArray::F64(mut vertices), FaceArray::I32(mut faces), VertexArray::F64(mut normals)) => {
            println!("F64 vertices, I32 faces");
            context_aware_smoothing_internal(
                vertices.as_array_mut(),
                faces.as_array_mut(),
                normals.as_array_mut(),
                t,
                tmax,
                bmin,
                n_iters,
            );
            Ok(())
        }
        // F64 vertices, U32 faces
        (VertexArray::F64(mut vertices), FaceArray::U32(mut faces), VertexArray::F32(mut normals)) => {
            println!("F64 vertices, U32 faces");
            context_aware_smoothing_internal(
                vertices.as_array_mut(),
                faces.as_array_mut(),
                normals.as_array_mut(),
                t,
                tmax,
                bmin,
                n_iters,
            );
            Ok(())
        }
        (VertexArray::F64(mut vertices), FaceArray::U32(mut faces), VertexArray::F64(mut normals)) => {
            println!("F64 vertices, U32 faces");
            context_aware_smoothing_internal(
                vertices.as_array_mut(),
                faces.as_array_mut(),
                normals.as_array_mut(),
                t,
                tmax,
                bmin,
                n_iters,
            );
            Ok(())
        }
    }
}