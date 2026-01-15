use crate::types::{NormalT, VertexIdT, VertexT};
use nalgebra::{Point3, Vector3};
use numpy::{PyReadonlyArray2, ToPyArray, ndarray};
use pyo3::prelude::*;
use std::collections::{HashMap, HashSet, VecDeque};

#[pyclass]
pub struct Mesh {
    vertices: ndarray::Array2<VertexT>,
    faces: ndarray::Array2<VertexIdT>,
    normals: ndarray::Array2<NormalT>,
    map_vface: HashMap<usize, Vec<usize>>,
    border_vertices: HashSet<usize>,
}

#[pymethods]
impl Mesh {
    #[new]
    fn new(
        vertices: PyReadonlyArray2<VertexT>,
        faces: PyReadonlyArray2<VertexIdT>,
        normals: PyReadonlyArray2<NormalT>,
    ) -> PyResult<Self> {
        let vertices_arr = vertices.as_array().to_owned();
        let faces_arr = faces.as_array().to_owned();
        let normals_arr = normals.as_array().to_owned();

        let mut map_vface: HashMap<usize, Vec<usize>> = HashMap::new();
        let mut edge_nfaces: HashMap<(VertexIdT, VertexIdT), i32> = HashMap::new();
        let mut border_vertices: HashSet<usize> = HashSet::new();

        for (i, face) in faces_arr.outer_iter().enumerate() {
            let v1 = face[1] as usize;
            let v2 = face[2] as usize;
            let v3 = face[3] as usize;

            map_vface.entry(v1).or_default().push(i);
            map_vface.entry(v2).or_default().push(i);
            map_vface.entry(v3).or_default().push(i);

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
                border_vertices.insert(edge.0 as usize);
                border_vertices.insert(edge.1 as usize);
            }
        }

        Ok(Self {
            vertices: vertices_arr,
            faces: faces_arr,
            normals: normals_arr,
            map_vface,
            border_vertices,
        })
    }

    #[getter]
    fn vertices<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, numpy::PyArray2<VertexT>>> {
        Ok(self.vertices.to_pyarray(py).into())
    }

    #[getter]
    fn faces<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, numpy::PyArray2<VertexIdT>>> {
        Ok(self.faces.to_pyarray(py).into())
    }

    #[getter]
    fn normals<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, numpy::PyArray2<NormalT>>> {
        Ok(self.normals.to_pyarray(py).into())
    }

    pub fn to_tuple<'py>(&self, py: Python<'py>) -> PyResult<(
        Bound<'py, numpy::PyArray2<VertexT>>,
        Bound<'py, numpy::PyArray2<VertexIdT>>,
        Bound<'py, numpy::PyArray2<NormalT>>
    )> {
        Ok((
            self.vertices.to_pyarray(py).into(),
            self.faces.to_pyarray(py).into(),
            self.normals.to_pyarray(py).into(),
        ))
    }

    pub fn find_staircase_artifacts(
        &self,
        stack_orientation: [f64; 3],
        t: f64,
    ) -> PyResult<Vec<usize>> {
        let n_vertices = self.vertices.shape()[0];
        let stack_orientation = Vector3::from_row_slice(&stack_orientation);

        let mut output = Vec::new();

        for v_id in 0..n_vertices {
            let mut max_z = -10000.0;
            let mut min_z = 10000.0;
            let mut max_y = -10000.0;
            let mut min_y = 10000.0;
            let mut max_x = -10000.0;
            let mut min_x = 10000.0;

            if let Some(f_ids) = self.map_vface.get(&v_id) {
                for &f_id in f_ids {
                    let normal = self.normals.row(f_id);
                    let normal_vec = Vector3::new(normal[0] as f64, normal[1] as f64, normal[2] as f64);

                    let of_z = 1.0 - (normal_vec.dot(&stack_orientation)).abs();
                    let of_y = 1.0 - (normal_vec.dot(&Vector3::new(0.0, 1.0, 0.0))).abs();
                    let of_x = 1.0 - (normal_vec.dot(&Vector3::new(1.0, 0.0, 0.0))).abs();

                    if of_z > max_z { max_z = of_z; }
                    if of_z < min_z { min_z = of_z; }
                    if of_y > max_y { max_y = of_y; }
                    if of_y < min_y { min_y = of_y; }
                    if of_x > max_x { max_x = of_x; }
                    if of_x < min_x { min_x = of_x; }

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
        Ok(output)
    }

    pub fn ca_smoothing(
        &mut self,
        t: f64,
        tmax: f32,
        bmin: f32,
        n_iters: i32,
    ) -> PyResult<()> {
        let stack_orientation = [0.0, 0.0, 1.0];
        let vertices_staircase = self.find_staircase_artifacts(stack_orientation, t)?;

        let weights = self.calc_artifacts_weight(&vertices_staircase, tmax, bmin);

        self.taubin_smooth(&weights, 0.5, -0.53, n_iters);

        Ok(())
    }
}

impl Mesh {
    fn get_ring1(&self, v_id: usize) -> HashSet<usize> {
        let mut ring1 = HashSet::new();
        if let Some(f_ids) = self.map_vface.get(&v_id) {
            for &f_id in f_ids {
                let face = self.faces.row(f_id);
                for i in 1..4 {
                    let v = face[i] as usize;
                    if v != v_id {
                        ring1.insert(v);
                    }
                }
            }
        }
        ring1
    }

    fn is_border(&self, v_id: usize) -> bool {
        self.border_vertices.contains(&v_id)
    }

    fn get_near_vertices_to_v(&self, v_id: usize, dmax: f32) -> Vec<usize> {
        let mut near_vertices = Vec::new();
        let mut to_visit = VecDeque::new();
        let mut status_v = HashSet::new();

        let v_i = self.vertices.row(v_id);
        let p_i = Point3::new(v_i[0], v_i[1], v_i[2]);
        
        to_visit.push_back(v_id);
        status_v.insert(v_id);

        let dmax_sq = dmax * dmax;

        while let Some(current_v_id) = to_visit.pop_front() {
            if let Some(f_ids) = self.map_vface.get(&current_v_id) {
                for &f_id in f_ids {
                    let face = self.faces.row(f_id);
                    for i in 1..4 {
                        let v_j_id = face[i] as usize;
                        if !status_v.contains(&v_j_id) {
                            status_v.insert(v_j_id);
                            let v_j = self.vertices.row(v_j_id);
                            let p_j = Point3::new(v_j[0], v_j[1], v_j[2]);
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
        tmax: f32,
        bmin: f32,
    ) -> Vec<f32> {
        let n_vertices = self.vertices.shape()[0];
        let mut weights = vec![bmin; n_vertices];

        for &vi_id in vertices_staircase {
            weights[vi_id] = 1.0;

            let near_vertices = self.get_near_vertices_to_v(vi_id, tmax);
            let vi = self.vertices.row(vi_id);
            let p_vi = Point3::new(vi[0], vi[1], vi[2]);

            for &vj_id in &near_vertices {
                let vj = self.vertices.row(vj_id);
                let p_vj = Point3::new(vj[0], vj[1], vj[2]);
                let d = (p_vi - p_vj).norm();
                let value = (1.0 - d / tmax) * (1.0 - bmin) + bmin;
                
                if value > weights[vj_id] {
                    weights[vj_id] = value;
                }
            }
        }

        weights
    }

    fn calc_d(&self, v_id: usize) -> Vector3<f32> {
        let vi = self.vertices.row(v_id);
        let p_vi = Point3::new(vi[0], vi[1], vi[2]);
        
        let ring1 = self.get_ring1(v_id);
        let mut d = Vector3::zeros();
        let mut n = 0.0f32;

        if self.is_border(v_id) {
            for &vj_id in &ring1 {
                if self.is_border(vj_id) {
                    let vj = self.vertices.row(vj_id);
                    let p_vj = Point3::new(vj[0], vj[1], vj[2]);
                    d += p_vi - p_vj;
                    n += 1.0;
                }
            }
        } else {
            for &vj_id in &ring1 {
                let vj = self.vertices.row(vj_id);
                let p_vj = Point3::new(vj[0], vj[1], vj[2]);
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

    fn taubin_smooth(&mut self, weights: &[f32], l: f32, m: f32, steps: i32) {
        let n_vertices = self.vertices.shape()[0];
        
        for _ in 0..steps {
            // Calculate D for all vertices
            let d_values: Vec<Vector3<f32>> = (0..n_vertices)
                .map(|i| self.calc_d(i))
                .collect();
            
            // Apply first smoothing step (lambda)
            for i in 0..n_vertices {
                self.vertices[[i, 0]] += weights[i] * l * d_values[i].x;
                self.vertices[[i, 1]] += weights[i] * l * d_values[i].y;
                self.vertices[[i, 2]] += weights[i] * l * d_values[i].z;
            }
            
            // Recalculate D
            let d_values: Vec<Vector3<f32>> = (0..n_vertices)
                .map(|i| self.calc_d(i))
                .collect();
            
            // Apply second smoothing step (mu)
            for i in 0..n_vertices {
                self.vertices[[i, 0]] += weights[i] * m * d_values[i].x;
                self.vertices[[i, 1]] += weights[i] * m * d_values[i].y;
                self.vertices[[i, 2]] += weights[i] * m * d_values[i].z;
            }
        }
    }
}
