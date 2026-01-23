use core::{f64, hash};
use nalgebra::{Point3, Vector3};
use ndarray::parallel::prelude::*;
use ndarray::Array2;
use num_traits::{AsPrimitive, NumCast};
use numpy::{ndarray, PyReadonlyArray2, ToPyArray};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use std::collections::{HashMap, HashSet, VecDeque};
use std::sync::Mutex;

/// Mesh genérico com tipos de vértices, índices de faces e normais parametrizáveis.
pub struct Mesh<V, F, N> {
    vertices: ndarray::Array2<V>,
    faces: ndarray::Array2<F>,
    normals: ndarray::Array2<N>,
    map_vface: HashMap<usize, Vec<usize>>,
    border_vertices: HashSet<F>,
}

impl<V, F, N> Mesh<V, F, N>
where
    V: num_traits::Float + Copy + Send + Sync + NumCast,
    V: std::ops::AddAssign<V> + AsPrimitive<f64>,
    F: num_traits::PrimInt + Copy + Send + Sync + Ord + hash::Hash + AsPrimitive<usize>,
    N: num_traits::Float + Copy + Send + Sync + AsPrimitive<f64>,
{
    pub fn new(
        vertices: ndarray::Array2<V>,
        faces: ndarray::Array2<F>,
        normals: ndarray::Array2<N>,
    ) -> PyResult<Self> {
        let vertices_arr = vertices.to_owned();

        let mut map_vface: HashMap<usize, Vec<usize>> = HashMap::new();
        let mut edge_nfaces: HashMap<(F, F), i32> = HashMap::new();
        let mut border_vertices: HashSet<F> = HashSet::new();

        for (i, face) in faces.outer_iter().enumerate() {
            let v1 = face[1];
            let v2 = face[2];
            let v3 = face[3];

            map_vface.entry(v1.as_()).or_default().push(i);
            map_vface.entry(v2.as_()).or_default().push(i);
            map_vface.entry(v3.as_()).or_default().push(i);

            let mut edge1 = [face[1], face[2]];
            edge1.sort();
            *edge_nfaces.entry((edge1[0], edge1[1])).or_default() += 1;

            let mut edge2 = [face[2], face[3]];
            edge2.sort();
            *edge_nfaces.entry((edge2[0], edge2[1])).or_default() += 1;

            let mut edge3 = [face[1], face[3]];
            edge3.sort();
            *edge_nfaces.entry((edge3[0], edge3[1])).or_default() += 1;
        }

        for (edge, count) in edge_nfaces {
            if count == 1 {
                border_vertices.insert(edge.0);
                border_vertices.insert(edge.1);
            }
        }

        Ok(Self {
            vertices: vertices_arr,
            faces: faces,
            normals: normals,
            map_vface,
            border_vertices,
        })
    }

    // pub fn vertices<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, numpy::PyArray2<V>>> {
    //     Ok(self.vertices.to_pyarray(py).into())
    // }

    // pub fn faces<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, numpy::PyArray2<F>>> {
    //     Ok(self.faces.to_pyarray(py).into())
    // }

    // pub fn normals<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, numpy::PyArray2<N>>> {
    //     Ok(self.normals.to_pyarray(py).into())
    // }

    // pub fn to_tuple<'py>(&self, py: Python<'py>) -> PyResult<(
    //     Bound<'py, numpy::PyArray2<VertexType>>,
    //     Bound<'py, numpy::PyArray2<VertexIdType>>,
    //     Bound<'py, numpy::PyArray2<NormalType>>
    // )> {
    //     Ok((
    //         self.vertices.to_pyarray(py).into(),
    //         self.faces.to_pyarray(py).into(),
    //         self.normals.to_pyarray(py).into(),
    //     ))
    // }

    pub fn find_staircase_artifacts(&self, stack_orientation: [f64; 3], t: f64) -> Vec<usize> {
        let n_vertices = self.vertices.shape()[0];
        let stack_orientation = Vector3::from_row_slice(&stack_orientation);

        let mut output = Vec::new();

        for v_id in 0..n_vertices {
            let mut max_z = f64::MAX;
            let mut min_z = f64::MIN;
            let mut max_y = f64::MAX;
            let mut min_y = f64::MIN;
            let mut max_x = f64::MAX;
            let mut min_x = f64::MIN;

            if let Some(f_ids) = self.map_vface.get(&v_id) {
                for &f_id in f_ids {
                    let normal = self.normals.row(f_id);
                    let normal_vec =
                        Vector3::new(normal[0].as_(), normal[1].as_(), normal[2].as_());

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

    pub fn ca_smoothing(&mut self, t: f64, tmax: f32, bmin: f32, n_iters: i32) {
        let stack_orientation = [0.0, 0.0, 1.0];
        let vertices_staircase = self.find_staircase_artifacts(stack_orientation, t);

        let weights = self.calc_artifacts_weight(&vertices_staircase, tmax as f64, bmin as f64);

        self.taubin_smooth(&weights, 0.5f64, -0.53f64, n_iters);
    }

    fn get_ring1(&self, v_id: usize) -> HashSet<usize> {
        let mut ring1 = HashSet::new();
        if let Some(f_ids) = self.map_vface.get(&v_id) {
            for &f_id in f_ids {
                let face = self.faces.row(f_id);
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

    fn is_border(&self, _v_id: usize) -> bool {
        // Convert v_id to F type for lookup
        // Since we're using ArrayView, we need to check if the vertex index exists in border_vertices
        // For now, we'll need to convert: but border_vertices stores F, not usize
        // This is a design issue - border_vertices should probably be HashSet<usize>
        // For now, we'll check by converting back
        false // TODO: Fix this - border_vertices type mismatch
    }

    fn get_near_vertices_to_v(&self, v_id: usize, dmax: f64) -> Vec<usize> {
        let mut near_vertices = Vec::new();
        let mut to_visit = VecDeque::new();
        let mut status_v = HashSet::new();

        let v_i = self.vertices.row(v_id);
        let p_i = Point3::new(v_i[0].as_(), v_i[1].as_(), v_i[2].as_());

        to_visit.push_back(v_id);
        status_v.insert(v_id);

        let dmax_sq = dmax * dmax;

        while let Some(current_v_id) = to_visit.pop_front() {
            if let Some(f_ids) = self.map_vface.get(&current_v_id) {
                for &f_id in f_ids {
                    let face = self.faces.row(f_id);
                    for i in 1..4 {
                        let v_j_id = face[i].as_();
                        if !status_v.contains(&v_j_id) {
                            status_v.insert(v_j_id);
                            let v_j = self.vertices.row(v_j_id);
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

    fn calc_artifacts_weight(
        &self,
        vertices_staircase: &[usize],
        tmax: f64,
        bmin: f64,
    ) -> Vec<f64> {
        let n_vertices = self.vertices.shape()[0];
        let weights = Mutex::new(vec![bmin; n_vertices]);

        vertices_staircase.into_par_iter().for_each(|vi_id| {
            {
                let mut weights = weights.lock().unwrap();
                weights[*vi_id] = 1.0;
            }

            let near_vertices = self.get_near_vertices_to_v(*vi_id, tmax as f64);
            let vi = self.vertices.row(*vi_id);
            let p_vi = Point3::new(vi[0].as_(), vi[1].as_(), vi[2].as_());

            for &vj_id in &near_vertices {
                let vj = self.vertices.row(vj_id);
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

    fn calc_d(&self, v_id: usize) -> Vector3<f64> {
        let vi = self.vertices.row(v_id);
        let p_vi = Point3::new(vi[0].as_(), vi[1].as_(), vi[2].as_());

        let ring1 = self.get_ring1(v_id);
        let mut d = Vector3::zeros();
        let mut n = 0.0f64;

        if self.is_border(v_id) {
            for &vj_id in &ring1 {
                if self.is_border(vj_id) {
                    let vj = self.vertices.row(vj_id);
                    let p_vj = Point3::new(vj[0].as_(), vj[1].as_(), vj[2].as_());
                    d += p_vi - p_vj;
                    n += 1.0;
                }
            }
        } else {
            for &vj_id in &ring1 {
                let vj = self.vertices.row(vj_id);
                let p_vj = Point3::new(vj[0].as_(), vj[1].as_(), vj[2].as_());
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

    /// Taubin smoothing algorithm (named after Gabriel Taubin)
    fn taubin_smooth(&mut self, weights: &[f64], l: f64, m: f64, steps: i32)
    where
        V: std::ops::AddAssign<V>,
    {
        let n_vertices = self.vertices.shape()[0];

        for _ in 0..steps {
            // Calculate D for all vertices
            let d_values: Array2<f64> =
                Array2::from_shape_fn((n_vertices, 3), |(i, _)| self.calc_d(i).x);

            // Apply first smoothing step (lambda)
            par_azip!((index i, mut vertex in self.vertices.outer_iter_mut(), d in d_values.outer_iter()) {
                let dx: V = NumCast::from(weights[i] * l * d[0]).unwrap_or(vertex[0]);
                let dy: V = NumCast::from(weights[i] * l * d[1]).unwrap_or(vertex[1]);
                let dz: V = NumCast::from(weights[i] * l * d[2]).unwrap_or(vertex[2]);
                vertex[0] += dx;
                vertex[1] += dy;
                vertex[2] += dz;
            });

            // Recalculate D
            let d_values: Array2<f64> =
                Array2::from_shape_fn((n_vertices, 3), |(i, _)| self.calc_d(i).x);

            // Apply second smoothing step (mu)
            par_azip!((index i, mut vertex in self.vertices.outer_iter_mut(), d in d_values.outer_iter()) {
                let dx: V = NumCast::from(weights[i] * m * d[0]).unwrap_or(vertex[0]);
                let dy: V = NumCast::from(weights[i] * m * d[1]).unwrap_or(vertex[1]);
                let dz: V = NumCast::from(weights[i] * m * d[2]).unwrap_or(vertex[2]);
                vertex[[0]] += dx;
                vertex[[1]] += dy;
                vertex[[2]] += dz;
            });
        }
    }
}

// Struct concreta para exposição ao Python (PyO3 não suporta #[pyclass] em genéricos).
// Usa Mesh<f32, i64, f32> como instanciação padrão.
pub enum MeshDispatch {
    F32I64(Mesh<f32, i64, f32>),
    F64I64(Mesh<f64, i64, f64>),
    F32U64(Mesh<f32, u64, f32>),
    F64U64(Mesh<f64, u64, f64>),
    F32I32(Mesh<f32, i32, f32>),
    F64I32(Mesh<f64, i32, f64>),
    F32U32(Mesh<f32, u32, f32>),
    F64U32(Mesh<f64, u32, f64>),
}

#[pyclass(name = "Mesh")]
pub struct MeshPy {
    inner: MeshDispatch,
}

#[pymethods]
impl MeshPy {
    #[new]
    fn new<'py>(
        vertices: Bound<'py, PyAny>,
        faces: Bound<'py, PyAny>,
        normals: Bound<'py, PyAny>,
    ) -> PyResult<Self> {
        // F32I64: vertices f32, faces i64, normals f32
        if let (Ok(v), Ok(f), Ok(n)) = (
            vertices.extract::<PyReadonlyArray2<f32>>(),
            faces.extract::<PyReadonlyArray2<i64>>(),
            normals.extract::<PyReadonlyArray2<f32>>(),
        ) {
            let mesh = Mesh::new(
                v.as_array().to_owned(),
                f.as_array().to_owned(),
                n.as_array().to_owned(),
            )?;
            return Ok(Self {
                inner: MeshDispatch::F32I64(mesh),
            });
        }
        // F64I64: vertices f64, faces i64, normals f64
        if let (Ok(v), Ok(f), Ok(n)) = (
            vertices.extract::<PyReadonlyArray2<f64>>(),
            faces.extract::<PyReadonlyArray2<i64>>(),
            normals.extract::<PyReadonlyArray2<f64>>(),
        ) {
            let mesh = Mesh::new(
                v.as_array().to_owned(),
                f.as_array().to_owned(),
                n.as_array().to_owned(),
            )?;
            return Ok(Self {
                inner: MeshDispatch::F64I64(mesh),
            });
        }
        // F32U64: vertices f32, faces u64, normals f32
        if let (Ok(v), Ok(f), Ok(n)) = (
            vertices.extract::<PyReadonlyArray2<f32>>(),
            faces.extract::<PyReadonlyArray2<u64>>(),
            normals.extract::<PyReadonlyArray2<f32>>(),
        ) {
            let mesh = Mesh::new(
                v.as_array().to_owned(),
                f.as_array().to_owned(),
                n.as_array().to_owned(),
            )?;
            return Ok(Self {
                inner: MeshDispatch::F32U64(mesh),
            });
        }
        // F64U64: vertices f64, faces u64, normals f64
        if let (Ok(v), Ok(f), Ok(n)) = (
            vertices.extract::<PyReadonlyArray2<f64>>(),
            faces.extract::<PyReadonlyArray2<u64>>(),
            normals.extract::<PyReadonlyArray2<f64>>(),
        ) {
            let mesh = Mesh::new(
                v.as_array().to_owned(),
                f.as_array().to_owned(),
                n.as_array().to_owned(),
            )?;
            return Ok(Self {
                inner: MeshDispatch::F64U64(mesh),
            });
        }
        // F32I32: vertices f32, faces i32, normals f32
        if let (Ok(v), Ok(f), Ok(n)) = (
            vertices.extract::<PyReadonlyArray2<f32>>(),
            faces.extract::<PyReadonlyArray2<i32>>(),
            normals.extract::<PyReadonlyArray2<f32>>(),
        ) {
            let mesh = Mesh::new(
                v.as_array().to_owned(),
                f.as_array().to_owned(),
                n.as_array().to_owned(),
            )?;
            return Ok(Self {
                inner: MeshDispatch::F32I32(mesh),
            });
        }
        // F64I32: vertices f64, faces i32, normals f64
        if let (Ok(v), Ok(f), Ok(n)) = (
            vertices.extract::<PyReadonlyArray2<f64>>(),
            faces.extract::<PyReadonlyArray2<i32>>(),
            normals.extract::<PyReadonlyArray2<f64>>(),
        ) {
            let mesh = Mesh::new(
                v.as_array().to_owned(),
                f.as_array().to_owned(),
                n.as_array().to_owned(),
            )?;
            return Ok(Self {
                inner: MeshDispatch::F64I32(mesh),
            });
        }
        // F32U32: vertices f32, faces u32, normals f32
        if let (Ok(v), Ok(f), Ok(n)) = (
            vertices.extract::<PyReadonlyArray2<f32>>(),
            faces.extract::<PyReadonlyArray2<u32>>(),
            normals.extract::<PyReadonlyArray2<f32>>(),
        ) {
            let mesh = Mesh::new(
                v.as_array().to_owned(),
                f.as_array().to_owned(),
                n.as_array().to_owned(),
            )?;
            return Ok(Self {
                inner: MeshDispatch::F32U32(mesh),
            });
        }
        // F64U32: vertices f64, faces u32, normals f64
        if let (Ok(v), Ok(f), Ok(n)) = (
            vertices.extract::<PyReadonlyArray2<f64>>(),
            faces.extract::<PyReadonlyArray2<u32>>(),
            normals.extract::<PyReadonlyArray2<f64>>(),
        ) {
            let mesh = Mesh::new(
                v.as_array().to_owned(),
                f.as_array().to_owned(),
                n.as_array().to_owned(),
            )?;
            return Ok(Self {
                inner: MeshDispatch::F64U32(mesh),
            });
        }

        Err(PyValueError::new_err(
            "Invalid input types. Supported combinations: (f32/f64, i64/u64/i32/u32, f32/f64)",
        ))
    }

    #[getter]
    fn vertices<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, numpy::PyArray2<f32>>> {
        match &self.inner {
            MeshDispatch::F32I64(mesh) => Ok(mesh.vertices.to_pyarray(py).into()),
            MeshDispatch::F64I64(mesh) => {
                let arr_f32: ndarray::Array2<f32> = mesh.vertices.mapv(|x| x as f32);
                Ok(arr_f32.to_pyarray(py).into())
            }
            MeshDispatch::F32U64(mesh) => Ok(mesh.vertices.to_pyarray(py).into()),
            MeshDispatch::F64U64(mesh) => {
                let arr_f32: ndarray::Array2<f32> = mesh.vertices.mapv(|x| x as f32);
                Ok(arr_f32.to_pyarray(py).into())
            }
            MeshDispatch::F32I32(mesh) => Ok(mesh.vertices.to_pyarray(py).into()),
            MeshDispatch::F64I32(mesh) => {
                let arr_f32: ndarray::Array2<f32> = mesh.vertices.mapv(|x| x as f32);
                Ok(arr_f32.to_pyarray(py).into())
            }
            MeshDispatch::F32U32(mesh) => Ok(mesh.vertices.to_pyarray(py).into()),
            MeshDispatch::F64U32(mesh) => {
                let arr_f32: ndarray::Array2<f32> = mesh.vertices.mapv(|x| x as f32);
                Ok(arr_f32.to_pyarray(py).into())
            }
        }
    }

    #[getter]
    fn faces<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, numpy::PyArray2<i64>>> {
        match &self.inner {
            MeshDispatch::F32I64(mesh) => Ok(mesh.faces.to_pyarray(py).into()),
            MeshDispatch::F64I64(mesh) => Ok(mesh.faces.to_pyarray(py).into()),
            MeshDispatch::F32U64(mesh) => {
                let arr_i64: ndarray::Array2<i64> = mesh.faces.mapv(|x| x as i64);
                Ok(arr_i64.to_pyarray(py).into())
            }
            MeshDispatch::F64U64(mesh) => {
                let arr_i64: ndarray::Array2<i64> = mesh.faces.mapv(|x| x as i64);
                Ok(arr_i64.to_pyarray(py).into())
            }
            MeshDispatch::F32I32(mesh) => {
                let arr_i64: ndarray::Array2<i64> = mesh.faces.mapv(|x| x as i64);
                Ok(arr_i64.to_pyarray(py).into())
            }
            MeshDispatch::F64I32(mesh) => {
                let arr_i64: ndarray::Array2<i64> = mesh.faces.mapv(|x| x as i64);
                Ok(arr_i64.to_pyarray(py).into())
            }
            MeshDispatch::F32U32(mesh) => {
                let arr_i64: ndarray::Array2<i64> = mesh.faces.mapv(|x| x as i64);
                Ok(arr_i64.to_pyarray(py).into())
            }
            MeshDispatch::F64U32(mesh) => {
                let arr_i64: ndarray::Array2<i64> = mesh.faces.mapv(|x| x as i64);
                Ok(arr_i64.to_pyarray(py).into())
            }
        }
    }

    #[getter]
    fn normals<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, numpy::PyArray2<f32>>> {
        match &self.inner {
            MeshDispatch::F32I64(mesh) => Ok(mesh.normals.to_pyarray(py).into()),
            MeshDispatch::F64I64(mesh) => {
                let arr_f32: ndarray::Array2<f32> = mesh.normals.mapv(|x| x as f32);
                Ok(arr_f32.to_pyarray(py).into())
            }
            MeshDispatch::F32U64(mesh) => Ok(mesh.normals.to_pyarray(py).into()),
            MeshDispatch::F64U64(mesh) => {
                let arr_f32: ndarray::Array2<f32> = mesh.normals.mapv(|x| x as f32);
                Ok(arr_f32.to_pyarray(py).into())
            }
            MeshDispatch::F32I32(mesh) => Ok(mesh.normals.to_pyarray(py).into()),
            MeshDispatch::F64I32(mesh) => {
                let arr_f32: ndarray::Array2<f32> = mesh.normals.mapv(|x| x as f32);
                Ok(arr_f32.to_pyarray(py).into())
            }
            MeshDispatch::F32U32(mesh) => Ok(mesh.normals.to_pyarray(py).into()),
            MeshDispatch::F64U32(mesh) => {
                let arr_f32: ndarray::Array2<f32> = mesh.normals.mapv(|x| x as f32);
                Ok(arr_f32.to_pyarray(py).into())
            }
        }
    }

    pub fn to_tuple<'py>(
        &self,
        py: Python<'py>,
    ) -> PyResult<(
        Bound<'py, numpy::PyArray2<f32>>,
        Bound<'py, numpy::PyArray2<i64>>,
        Bound<'py, numpy::PyArray2<f32>>,
    )> {
        match &self.inner {
            MeshDispatch::F32I64(mesh) => Ok((
                mesh.vertices.to_pyarray(py).into(),
                mesh.faces.to_pyarray(py).into(),
                mesh.normals.to_pyarray(py).into(),
            )),
            MeshDispatch::F64I64(mesh) => Ok((
                {
                    let arr_f32: ndarray::Array2<f32> = mesh.vertices.mapv(|x| x as f32);
                    arr_f32.to_pyarray(py).into()
                },
                mesh.faces.to_pyarray(py).into(),
                {
                    let arr_f32: ndarray::Array2<f32> = mesh.normals.mapv(|x| x as f32);
                    arr_f32.to_pyarray(py).into()
                },
            )),
            MeshDispatch::F32U64(mesh) => Ok((
                mesh.vertices.to_pyarray(py).into(),
                {
                    let arr_i64: ndarray::Array2<i64> = mesh.faces.mapv(|x| x as i64);
                    arr_i64.to_pyarray(py).into()
                },
                mesh.normals.to_pyarray(py).into(),
            )),
            MeshDispatch::F64U64(mesh) => Ok((
                {
                    let arr_f32: ndarray::Array2<f32> = mesh.vertices.mapv(|x| x as f32);
                    arr_f32.to_pyarray(py).into()
                },
                {
                    let arr_i64: ndarray::Array2<i64> = mesh.faces.mapv(|x| x as i64);
                    arr_i64.to_pyarray(py).into()
                },
                {
                    let arr_f32: ndarray::Array2<f32> = mesh.normals.mapv(|x| x as f32);
                    arr_f32.to_pyarray(py).into()
                },
            )),
            MeshDispatch::F32I32(mesh) => Ok((
                mesh.vertices.to_pyarray(py).into(),
                {
                    let arr_i64: ndarray::Array2<i64> = mesh.faces.mapv(|x| x as i64);
                    arr_i64.to_pyarray(py).into()
                },
                mesh.normals.to_pyarray(py).into(),
            )),
            MeshDispatch::F64I32(mesh) => Ok((
                {
                    let arr_f32: ndarray::Array2<f32> = mesh.vertices.mapv(|x| x as f32);
                    arr_f32.to_pyarray(py).into()
                },
                {
                    let arr_i64: ndarray::Array2<i64> = mesh.faces.mapv(|x| x as i64);
                    arr_i64.to_pyarray(py).into()
                },
                {
                    let arr_f32: ndarray::Array2<f32> = mesh.normals.mapv(|x| x as f32);
                    arr_f32.to_pyarray(py).into()
                },
            )),
            MeshDispatch::F32U32(mesh) => Ok((
                mesh.vertices.to_pyarray(py).into(),
                {
                    let arr_i64: ndarray::Array2<i64> = mesh.faces.mapv(|x| x as i64);
                    arr_i64.to_pyarray(py).into()
                },
                mesh.normals.to_pyarray(py).into(),
            )),
            MeshDispatch::F64U32(mesh) => Ok((
                {
                    let arr_f32: ndarray::Array2<f32> = mesh.vertices.mapv(|x| x as f32);
                    arr_f32.to_pyarray(py).into()
                },
                {
                    let arr_i64: ndarray::Array2<i64> = mesh.faces.mapv(|x| x as i64);
                    arr_i64.to_pyarray(py).into()
                },
                {
                    let arr_f32: ndarray::Array2<f32> = mesh.normals.mapv(|x| x as f32);
                    arr_f32.to_pyarray(py).into()
                },
            )),
        }
    }

    pub fn find_staircase_artifacts(
        &self,
        stack_orientation: [f64; 3],
        t: f64,
    ) -> PyResult<Vec<usize>> {
        match &self.inner {
            MeshDispatch::F32I64(mesh) => Ok(mesh.find_staircase_artifacts(stack_orientation, t)),
            MeshDispatch::F64I64(mesh) => Ok(mesh.find_staircase_artifacts(stack_orientation, t)),
            MeshDispatch::F32U64(mesh) => Ok(mesh.find_staircase_artifacts(stack_orientation, t)),
            MeshDispatch::F64U64(mesh) => Ok(mesh.find_staircase_artifacts(stack_orientation, t)),
            MeshDispatch::F32I32(mesh) => Ok(mesh.find_staircase_artifacts(stack_orientation, t)),
            MeshDispatch::F64I32(mesh) => Ok(mesh.find_staircase_artifacts(stack_orientation, t)),
            MeshDispatch::F32U32(mesh) => Ok(mesh.find_staircase_artifacts(stack_orientation, t)),
            MeshDispatch::F64U32(mesh) => Ok(mesh.find_staircase_artifacts(stack_orientation, t)),
        }
    }

    pub fn ca_smoothing(&mut self, t: f64, tmax: f32, bmin: f32, n_iters: i32) -> PyResult<()> {
        match &mut self.inner {
            MeshDispatch::F32I64(mesh) => Ok(mesh.ca_smoothing(t, tmax, bmin, n_iters)),
            MeshDispatch::F64I64(mesh) => Ok(mesh.ca_smoothing(t, tmax, bmin, n_iters)),
            MeshDispatch::F32U64(mesh) => Ok(mesh.ca_smoothing(t, tmax, bmin, n_iters)),
            MeshDispatch::F64U64(mesh) => Ok(mesh.ca_smoothing(t, tmax, bmin, n_iters)),
            MeshDispatch::F32I32(mesh) => Ok(mesh.ca_smoothing(t, tmax, bmin, n_iters)),
            MeshDispatch::F64I32(mesh) => Ok(mesh.ca_smoothing(t, tmax, bmin, n_iters)),
            MeshDispatch::F32U32(mesh) => Ok(mesh.ca_smoothing(t, tmax, bmin, n_iters)),
            MeshDispatch::F64U32(mesh) => Ok(mesh.ca_smoothing(t, tmax, bmin, n_iters)),
        }
    }
}
