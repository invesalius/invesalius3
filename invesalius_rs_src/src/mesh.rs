use core::{f64, hash};
use nalgebra::Vector3;
use ndarray::parallel::prelude::*;
use ndarray::{Array2, ArrayView1, ArrayView2, ArrayViewMut2};
use num_traits::{AsPrimitive, NumCast};
use numpy::ndarray;
use pyo3::prelude::*;
use std::collections::{HashMap, HashSet};
use std::sync::atomic::{AtomicU64, AtomicUsize, Ordering};

use crate::types::{FaceArray, VertexArray};

pub trait Vertex:
    num_traits::Float + Copy + Send + Sync + NumCast + std::ops::AddAssign<Self> + AsPrimitive<f64>
{
}

impl Vertex for f32 {}
impl Vertex for f64 {}

pub trait Face:
    num_traits::PrimInt + Copy + Send + Sync + Ord + hash::Hash + AsPrimitive<usize>
{
}

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
    let t0 = std::time::Instant::now();
    let map_vface = build_map_vface(&faces.view());
    let t1 = std::time::Instant::now();
    println!("build_map_vface time: {:?}", t1.duration_since(t0));
    let t0 = std::time::Instant::now();
    let vertex_connectivity = build_vertex_connectivity(&faces.view(), &vertices.view());
    let t1 = std::time::Instant::now();
    println!(
        "build_vertex_connectivity time: {:?}",
        t1.duration_since(t0)
    );
    let _edge_nfaces: HashMap<(F, F), i32> = HashMap::new();
    let _border_vertices: HashSet<F> = HashSet::new();

    let stack_orientation = [0.0, 0.0, 1.0];
    let t0 = std::time::Instant::now();
    let vertices_staircase = find_staircase_artifacts(
        &vertices.view(),
        &faces.view(),
        &normals.view(),
        &map_vface,
        stack_orientation,
        t,
    );
    let t1 = std::time::Instant::now();
    println!("find_staircase_artifacts time: {:?}", t1.duration_since(t0));
    let t0 = std::time::Instant::now();
    let weights = propagate_weights(
        &vertices.view(),
        &vertex_connectivity,
        &vertices_staircase,
        tmax,
        bmin,
    );
    let t1 = std::time::Instant::now();
    println!("floodfill_mesh time: {:?}", t1.duration_since(t0));
    let t0 = std::time::Instant::now();
    taubin_smooth(
        vertices,
        &vertex_connectivity,
        &weights,
        0.5,
        -0.53,
        n_iters,
    );
    let t1 = std::time::Instant::now();
    println!("taubin_smooth time: {:?}", t1.duration_since(t0));
}

fn build_map_vface<F>(faces: &ArrayView2<F>) -> HashMap<usize, Vec<usize>>
where
    F: Face,
{
    let mut map_vface: HashMap<usize, Vec<usize>> = HashMap::with_capacity(faces.nrows());

    for (f_id, face) in faces.outer_iter().enumerate() {
        for &v_id in face.iter() {
            map_vface.entry(v_id.as_()).or_default().push(f_id);
        }
    }
    map_vface
}

fn build_vertex_connectivity<F, V>(
    faces: &ArrayView2<F>,
    vertices: &ArrayView2<V>,
) -> Vec<Vec<usize>>
where
    F: Face,
    V: Vertex,
{
    let mut vertex_connectivity = vec![vec![]; vertices.nrows()];

    for face in faces.outer_iter() {
        for &v_i in face.iter().skip(1) {
            for &v_j in face.iter().skip(1) {
                if v_i != v_j && !vertex_connectivity[v_i.as_()].contains(&v_j.as_()) {
                    vertex_connectivity[v_i.as_()].push(v_j.as_());
                }
            }
        }
    }
    vertex_connectivity
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

    let output = (0..n_vertices)
        .into_par_iter()
        .filter_map(|v_id: usize| {
            let mut max_z = f64::MIN;
            let mut min_z = f64::MAX;
            let mut max_y = f64::MIN;
            let mut min_y = f64::MAX;
            let mut max_x = f64::MIN;
            let mut min_x = f64::MAX;

            if let Some(f_ids) = map_vface.get(&v_id) {
                for &f_id in f_ids {
                    let normal = normals.row(f_id);
                    let normal_vec =
                        Vector3::new(normal[0].as_(), normal[1].as_(), normal[2].as_());

                    let of_z = 1.0 - (normal_vec.dot(&stack_orientation)).abs();
                    let of_y = 1.0 - (normal_vec.dot(&Vector3::new(0.0, 1.0, 0.0))).abs();
                    let of_x = 1.0 - (normal_vec.dot(&Vector3::new(1.0, 0.0, 0.0))).abs();

                    if of_z > max_z {
                        max_z = of_z;
                    } else if of_z < min_z {
                        min_z = of_z;
                    }
                    if of_y > max_y {
                        max_y = of_y;
                    } else if of_y < min_y {
                        min_y = of_y;
                    }
                    if of_x > max_x {
                        max_x = of_x;
                    } else if of_x < min_x {
                        min_x = of_x;
                    }

                    if (max_z - min_z).abs() >= t
                        || (max_y - min_y).abs() >= t
                        || (max_x - min_x).abs() >= t
                    {
                        return Some(v_id);
                    }
                }
            }
            None
        })
        .collect::<Vec<usize>>();
    output
}

fn sqdist<V>(a: &ArrayView1<V>, b: &ArrayView1<V>) -> f64
where
    V: Vertex,
{
    let dx = a[0].as_() - b[0].as_();
    let dy = a[1].as_() - b[1].as_();
    let dz = a[2].as_() - b[2].as_();

    dx * dx + dy * dy + dz * dz
}

pub fn propagate_weights<V>(
    positions: &ArrayView2<V>,
    adjacency: &[Vec<usize>],
    seeds: &[usize],
    tmax: f64,
    bmin: f64,
) -> Vec<f64>
where
    V: Vertex,
{
    let n = positions.shape()[0];

    let dist = (0..n)
        .map(|_| AtomicU64::new(f64::INFINITY.to_bits()))
        .collect::<Vec<_>>();

    let seed_map = (0..n)
        .map(|_| AtomicUsize::new(usize::MAX))
        .collect::<Vec<_>>();

    let mut frontier = seeds.to_vec();

    for &s in seeds {
        dist[s].store(0f64.to_bits(), Ordering::Relaxed);
        seed_map[s].store(s, Ordering::Relaxed);
    }

    let tmax_sq = tmax * tmax;

    while !frontier.is_empty() {
        let next: Vec<Vec<usize>> = frontier
            .par_iter()
            .map(|&v| {
                let mut local = Vec::new();

                let seed = seed_map[v].load(Ordering::Acquire);
                let seed_pos = &positions.row(seed);

                for &vj in &adjacency[v] {
                    let pj = &positions.row(vj);

                    let d_sq = sqdist(pj, seed_pos);

                    if d_sq > tmax_sq {
                        continue;
                    }

                    loop {
                        let old = f64::from_bits(dist[vj].load(Ordering::Acquire));

                        if d_sq >= old && old.is_finite() {
                            break;
                        }

                        if dist[vj]
                            .compare_exchange_weak(
                                old.to_bits(),
                                d_sq.to_bits(),
                                Ordering::AcqRel,
                                Ordering::Acquire,
                            )
                            .is_ok()
                        {
                            seed_map[vj].store(seed, Ordering::Release);

                            local.push(vj);
                            break;
                        }
                    }
                }

                local
            })
            .collect();
        frontier = next.into_iter().flatten().collect();
    }

    // cálculo final do weight

    (0..n)
        .map(|i| {
            let d = f64::from_bits(dist[i].load(Ordering::Relaxed));

            if !d.is_finite() {
                return bmin;
            }

            let d = d.sqrt();

            (1.0 - d / tmax) * (1.0 - bmin) + bmin
        })
        .collect()
}

#[inline]
fn calc_d<V>(
    vertices: &ArrayView2<V>,
    vertex_connectivity: &Vec<Vec<usize>>,
    v_id: usize,
) -> Vector3<f64>
where
    V: Vertex,
{
    let vi = vertices.row(v_id);
    let p_vi = Vector3::new(vi[0].as_(), vi[1].as_(), vi[2].as_());

    let mut d = Vector3::zeros();
    let mut n = 0usize;

    if is_border(v_id) {
        for &vj_id in vertex_connectivity[v_id].iter() {
            if is_border(vj_id) {
                let vj = vertices.row(vj_id);
                let p_vj = Vector3::new(vj[0].as_(), vj[1].as_(), vj[2].as_());
                d += p_vi - p_vj;
                n += 1;
            }
        }
    } else {
        for &vj_id in vertex_connectivity[v_id].iter() {
            let vj = vertices.row(vj_id);
            let p_vj = Vector3::new(vj[0].as_(), vj[1].as_(), vj[2].as_());
            d += p_vi - p_vj;
            n += 1;
        }
    }

    if n > 0 {
        d / n as f64
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

fn taubin_smooth<V>(
    mut vertices: ArrayViewMut2<V>,
    vertex_connectivity: &Vec<Vec<usize>>,
    weights: &Vec<f64>,
    l: f64,
    m: f64,
    steps: u32,
) where
    V: Vertex,
{
    let n_vertices = vertices.shape()[0];
    let mut d_values: Array2<f64> = Array2::zeros((n_vertices, 3));

    for _ in 0..steps {
        // Calculate D for all vertices

        par_azip!((index i, mut d in d_values.outer_iter_mut()) {
            let d_vec = calc_d(&vertices.view(), vertex_connectivity, i);
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
            let d_vec = calc_d(&vertices.view(),  vertex_connectivity, i);
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
        (
            VertexArray::F32(mut vertices),
            FaceArray::I64(mut faces),
            VertexArray::F32(mut normals),
        ) => {
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
        (
            VertexArray::F32(mut vertices),
            FaceArray::I64(mut faces),
            VertexArray::F64(mut normals),
        ) => {
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
        (
            VertexArray::F32(mut vertices),
            FaceArray::U64(mut faces),
            VertexArray::F32(mut normals),
        ) => {
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
        (
            VertexArray::F32(mut vertices),
            FaceArray::U64(mut faces),
            VertexArray::F64(mut normals),
        ) => {
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
        (
            VertexArray::F32(mut vertices),
            FaceArray::I32(mut faces),
            VertexArray::F32(mut normals),
        ) => {
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
        (
            VertexArray::F32(mut vertices),
            FaceArray::I32(mut faces),
            VertexArray::F64(mut normals),
        ) => {
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
        (
            VertexArray::F32(mut vertices),
            FaceArray::U32(mut faces),
            VertexArray::F32(mut normals),
        ) => {
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
        (
            VertexArray::F32(mut vertices),
            FaceArray::U32(mut faces),
            VertexArray::F64(mut normals),
        ) => {
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
        (
            VertexArray::F64(mut vertices),
            FaceArray::I64(mut faces),
            VertexArray::F32(mut normals),
        ) => {
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
        (
            VertexArray::F64(mut vertices),
            FaceArray::I64(mut faces),
            VertexArray::F64(mut normals),
        ) => {
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
        (
            VertexArray::F64(mut vertices),
            FaceArray::U64(mut faces),
            VertexArray::F32(mut normals),
        ) => {
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
        (
            VertexArray::F64(mut vertices),
            FaceArray::U64(mut faces),
            VertexArray::F64(mut normals),
        ) => {
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
        (
            VertexArray::F64(mut vertices),
            FaceArray::I32(mut faces),
            VertexArray::F32(mut normals),
        ) => {
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
        (
            VertexArray::F64(mut vertices),
            FaceArray::I32(mut faces),
            VertexArray::F64(mut normals),
        ) => {
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
        (
            VertexArray::F64(mut vertices),
            FaceArray::U32(mut faces),
            VertexArray::F32(mut normals),
        ) => {
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
        (
            VertexArray::F64(mut vertices),
            FaceArray::U32(mut faces),
            VertexArray::F64(mut normals),
        ) => {
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
