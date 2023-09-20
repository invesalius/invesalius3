#distutils: language = c++
#cython: boundscheck=False
#cython: wraparound=False
#cython: initializedcheck=False
#cython: cdivision=True
#cython: nonecheck=False

import os
import sys
import time
cimport numpy as np

from libc.math cimport sin, cos, acos, exp, sqrt, fabs, M_PI
from libc.stdlib cimport abs as cabs
from cython.operator cimport dereference as deref, preincrement as inc
from libcpp.map cimport map
from libcpp.unordered_map cimport unordered_map
from libcpp.set cimport set
from libcpp.vector cimport vector
from libcpp.pair cimport pair
from libcpp cimport bool
from libcpp.deque cimport deque as cdeque
from cython.parallel cimport prange
cimport openmp

from .cy_my_types cimport vertex_t, normal_t, vertex_id_t

import numpy as np

from vtkmodules.util import numpy_support
from vtkmodules.vtkCommonCore import vtkPoints
from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData

ctypedef float weight_t

cdef struct Point:
    vertex_t x
    vertex_t y
    vertex_t z

ctypedef pair[vertex_id_t, vertex_id_t] key


cdef class Mesh:
    cdef vertex_t[:, :] vertices
    cdef vertex_id_t[:, :] faces
    cdef normal_t[:, :] normals

    cdef unordered_map[int, vector[vertex_id_t]] map_vface
    cdef unordered_map[vertex_id_t, int] border_vertices

    cdef bool _initialized

    def __cinit__(self, pd=None, other=None):
        cdef int i
        cdef map[key, int] edge_nfaces
        cdef map[key, int].iterator it
        if pd:
            self._initialized = True
            _vertices = numpy_support.vtk_to_numpy(pd.GetPoints().GetData())
            _vertices.shape = -1, 3

            _faces = numpy_support.vtk_to_numpy(pd.GetPolys().GetData())
            _faces.shape = -1, 4

            _normals = numpy_support.vtk_to_numpy(pd.GetCellData().GetArray("Normals"))
            _normals.shape = -1, 3

            self.vertices = _vertices
            self.faces = _faces
            self.normals = _normals

            for i in range(_faces.shape[0]):
                self.map_vface[self.faces[i, 1]].push_back(i)
                self.map_vface[self.faces[i, 2]].push_back(i)
                self.map_vface[self.faces[i, 3]].push_back(i)

                edge_nfaces[key(min(self.faces[i, 1], self.faces[i, 2]), max(self.faces[i, 1], self.faces[i, 2]))] += 1
                edge_nfaces[key(min(self.faces[i, 2], self.faces[i, 3]), max(self.faces[i, 2], self.faces[i, 3]))] += 1
                edge_nfaces[key(min(self.faces[i, 1], self.faces[i, 3]), max(self.faces[i, 1], self.faces[i, 3]))] += 1

            it = edge_nfaces.begin()

            while it != edge_nfaces.end():
                if deref(it).second == 1:
                    self.border_vertices[deref(it).first.first] = 1
                    self.border_vertices[deref(it).first.second] = 1

                inc(it)

        elif other:
            _other = <Mesh>other
            self._initialized = True
            self.vertices = _other.vertices.copy()
            self.faces = _other.faces.copy()
            self.normals = _other.normals.copy()
            self.map_vface = unordered_map[int, vector[vertex_id_t]](_other.map_vface)
            self.border_vertices = unordered_map[vertex_id_t, int](_other.border_vertices)
        else:
            self._initialized = False

    cdef void copy_to(self, Mesh other):
        """
        Copies self content to other.
        """
        if self._initialized:
            other.vertices[:] = self.vertices
            other.faces[:] = self.faces
            other.normals[:] = self.normals
            other.map_vface = unordered_map[int, vector[vertex_id_t]](self.map_vface)
            other.border_vertices = unordered_map[vertex_id_t, int](self.border_vertices)
        else:
            other.vertices = self.vertices.copy()
            other.faces = self.faces.copy()
            other.normals = self.normals.copy()

            other.map_vface = self.map_vface
            other.border_vertices = self.border_vertices

    def to_vtk(self):
        """
        Converts Mesh to vtkPolyData.
        """
        vertices = np.asarray(self.vertices)
        faces = np.asarray(self.faces)
        normals = np.asarray(self.normals)

        points = vtkPoints()
        points.SetData(numpy_support.numpy_to_vtk(vertices))

        id_triangles = numpy_support.numpy_to_vtkIdTypeArray(faces)
        triangles = vtkCellArray()
        triangles.SetCells(faces.shape[0], id_triangles)

        pd = vtkPolyData()
        pd.SetPoints(points)
        pd.SetPolys(triangles)

        return pd

    cdef vector[vertex_id_t]* get_faces_by_vertex(self, int v_id) noexcept nogil:
        """
        Returns the faces whose vertex `v_id' is part.
        """
        return &self.map_vface[v_id]

    cdef set[vertex_id_t]* get_ring1(self, vertex_id_t v_id) noexcept nogil:
        """
        Returns the ring1 of vertex `v_id'
        """
        cdef vertex_id_t f_id
        cdef set[vertex_id_t]* ring1 = new set[vertex_id_t]()
        cdef vector[vertex_id_t].iterator it = self.map_vface[v_id].begin()

        while it != self.map_vface[v_id].end():
            f_id = deref(it)
            inc(it)
            if self.faces[f_id, 1] != v_id:
                ring1.insert(self.faces[f_id, 1])
            if self.faces[f_id, 2] != v_id:
                ring1.insert(self.faces[f_id, 2])
            if self.faces[f_id, 3] != v_id:
                ring1.insert(self.faces[f_id, 3])

        return ring1

    cdef bool is_border(self, vertex_id_t v_id) noexcept nogil:
        """
        Check if vertex `v_id' is a vertex border.
        """
        return self.border_vertices.find(v_id) != self.border_vertices.end()

    cdef vector[vertex_id_t]* get_near_vertices_to_v(self, vertex_id_t v_id, float dmax) noexcept nogil:
        """
        Returns all vertices with distance at most `d' to the vertex `v_id'

        Params:
            v_id: id of the vertex
            dmax: the maximum distance.
        """
        cdef vector[vertex_id_t]* idfaces
        cdef vector[vertex_id_t]* near_vertices = new vector[vertex_id_t]()

        cdef cdeque[vertex_id_t] to_visit
        cdef unordered_map[vertex_id_t, bool] status_v
        cdef unordered_map[vertex_id_t, bool] status_f

        cdef vertex_t *vip
        cdef vertex_t *vjp

        cdef float distance
        cdef int nf, nid, j
        cdef vertex_id_t f_id, vj

        vip = &self.vertices[v_id, 0]
        to_visit.push_back(v_id)
        dmax = dmax * dmax
        while(not to_visit.empty()):
            v_id = to_visit.front()
            to_visit.pop_front()

            status_v[v_id] = True

            idfaces = self.get_faces_by_vertex(v_id)
            nf = idfaces.size()

            for nid in range(nf):
                f_id = deref(idfaces)[nid]
                if status_f.find(f_id) == status_f.end():
                    status_f[f_id] = True

                    for j in range(3):
                        vj = self.faces[f_id, j+1]
                        if status_v.find(vj) == status_v.end():
                            status_v[vj] = True
                            vjp = &self.vertices[vj, 0]
                            distance = (vip[0] - vjp[0]) * (vip[0] - vjp[0]) \
                                + (vip[1] - vjp[1]) * (vip[1] - vjp[1]) \
                                + (vip[2] - vjp[2]) * (vip[2] - vjp[2])
                            if distance <= dmax:
                                near_vertices.push_back(vj)
                                to_visit.push_back(vj)

        return near_vertices


cdef vector[weight_t]* calc_artifacts_weight(Mesh mesh, vector[vertex_id_t]& vertices_staircase, float tmax, float bmin) noexcept nogil:
    """
    Calculate the artifact weight based on distance of each vertex to its
    nearest staircase artifact vertex.

    Params:
        mesh: Mesh
        vertices_staircase: the identified staircase artifact vertices
        tmax: max distance the vertex must be to its nearest artifact vertex
              to considered to calculate the weight
        bmin: The minimum weight.
    """
    cdef int vi_id, vj_id, nnv, n_ids, i, j
    cdef vector[vertex_id_t]* near_vertices
    cdef weight_t value
    cdef float d
    n_ids = vertices_staircase.size()

    cdef vertex_t* vi
    cdef vertex_t* vj
    cdef size_t msize

    msize = mesh.vertices.shape[0]
    cdef vector[weight_t]* weights = new vector[weight_t](msize)
    weights.assign(msize, bmin)

    cdef openmp.omp_lock_t lock
    openmp.omp_init_lock(&lock)

    for i in prange(n_ids, nogil=True):
        vi_id = vertices_staircase[i]
        deref(weights)[vi_id] = 1.0

        vi = &mesh.vertices[vi_id, 0]
        near_vertices = mesh.get_near_vertices_to_v(vi_id, tmax)
        nnv = near_vertices.size()

        for j in range(nnv):
            vj_id = deref(near_vertices)[j]
            vj = &mesh.vertices[vj_id, 0]

            d = sqrt((vi[0] - vj[0]) * (vi[0] - vj[0])\
                   + (vi[1] - vj[1]) * (vi[1] - vj[1])\
                   + (vi[2] - vj[2]) * (vi[2] - vj[2]))
            value = (1.0 - d/tmax) * (1.0 - bmin) + bmin

            if value > deref(weights)[vj_id]:
                openmp.omp_set_lock(&lock)
                deref(weights)[vj_id] = value
                openmp.omp_unset_lock(&lock)

        del near_vertices

    #  for i in range(msize):
        #  if mesh.is_border(i):
            #  deref(weights)[i] = 0.0

    #  cdef vertex_id_t v0, v1, v2
    #  for i in range(mesh.faces.shape[0]):
        #  for j in range(1, 4):
            #  v0 = mesh.faces[i, j]
            #  vi = &mesh.vertices[v0, 0]
            #  if mesh.is_border(v0):
                #  deref(weights)[v0] = 0.0
                #  v1 = mesh.faces[i, (j + 1) % 3 + 1]
                #  if mesh.is_border(v1):
                    #  vi = &mesh.vertices[v1, 0]
                    #  deref(weights)[v0] = 0.0

    openmp.omp_destroy_lock(&lock)
    return weights


cdef inline Point calc_d(Mesh mesh, vertex_id_t v_id) noexcept nogil:
    cdef Point D
    cdef int nf, f_id, nid
    cdef float n=0
    cdef int i
    cdef vertex_t* vi
    cdef vertex_t* vj
    cdef set[vertex_id_t]* vertices
    cdef set[vertex_id_t].iterator it
    cdef vertex_id_t vj_id

    D.x = 0.0
    D.y = 0.0
    D.z = 0.0

    vertices = mesh.get_ring1(v_id)
    vi = &mesh.vertices[v_id, 0]

    if mesh.is_border(v_id):
        it = vertices.begin()
        while it != vertices.end():
            vj_id = deref(it)
            if mesh.is_border(vj_id):
                vj = &mesh.vertices[vj_id, 0]

                D.x = D.x + (vi[0] - vj[0])
                D.y = D.y + (vi[1] - vj[1])
                D.z = D.z + (vi[2] - vj[2])
                n += 1.0

            inc(it)
    else:
        it = vertices.begin()
        while it != vertices.end():
            vj_id = deref(it)
            vj = &mesh.vertices[vj_id, 0]

            D.x = D.x + (vi[0] - vj[0])
            D.y = D.y + (vi[1] - vj[1])
            D.z = D.z + (vi[2] - vj[2])
            n += 1.0

            inc(it)

    del vertices

    D.x = D.x / n
    D.y = D.y / n
    D.z = D.z / n
    return D

cdef vector[vertex_id_t]* find_staircase_artifacts(Mesh mesh, double[3] stack_orientation, double T) noexcept nogil:
    """
    This function is used to find vertices at staircase artifacts, which are
    those vertices whose incident faces' orientation differences are
    greater than T.

    Params:
        mesh: Mesh
        stack_orientation: orientation of slice stacking
        T: Min angle (between vertex faces and stack_orientation) to consider a
           vertex a staircase artifact.
    """
    cdef int nv, nf, f_id, v_id
    cdef double of_z, of_y, of_x, min_z, max_z, min_y, max_y, min_x, max_x;
    cdef vector[vertex_id_t]* f_ids
    cdef normal_t* normal

    cdef vector[vertex_id_t]* output = new vector[vertex_id_t]()
    cdef int i

    nv = mesh.vertices.shape[0]

    for v_id in range(nv):
        max_z = -10000
        min_z = 10000
        max_y = -10000
        min_y = 10000
        max_x = -10000
        min_x = 10000

        f_ids = mesh.get_faces_by_vertex(v_id)
        nf = deref(f_ids).size()

        for i in range(nf):
            f_id = deref(f_ids)[i]
            normal = &mesh.normals[f_id, 0]

            of_z = 1 - fabs(normal[0]*stack_orientation[0] + normal[1]*stack_orientation[1] + normal[2]*stack_orientation[2]);
            of_y = 1 - fabs(normal[0]*0 + normal[1]*1 + normal[2]*0);
            of_x = 1 - fabs(normal[0]*1 + normal[1]*0 + normal[2]*0);

            if (of_z > max_z):
                max_z = of_z

            if (of_z < min_z):
                min_z = of_z

            if (of_y > max_y):
                max_y = of_y

            if (of_y < min_y):
                min_y = of_y

            if (of_x > max_x):
                max_x = of_x

            if (of_x < min_x):
                min_x = of_x


            if ((fabs(max_z - min_z) >= T) or (fabs(max_y - min_y) >= T) or (fabs(max_x - min_x) >= T)):
                output.push_back(v_id)
                break
    return output


cdef void taubin_smooth(Mesh mesh, vector[weight_t]& weights, float l, float m, int steps) nogil:
    """
    Implementation of Taubin's smooth algorithm described in the paper "A
    Signal Processing Approach To Fair Surface Design". His benefeat is it
    avoids surface shrinking.
    """
    cdef int s, i, nvertices
    nvertices = mesh.vertices.shape[0]
    cdef vector[Point] D = vector[Point](nvertices)
    cdef vertex_t* vi
    for s in range(steps):
        for i in prange(nvertices, nogil=True):
            D[i] = calc_d(mesh, i)

        for i in prange(nvertices, nogil=True):
            mesh.vertices[i, 0] += weights[i]*l*D[i].x;
            mesh.vertices[i, 1] += weights[i]*l*D[i].y;
            mesh.vertices[i, 2] += weights[i]*l*D[i].z;

        for i in prange(nvertices, nogil=True):
            D[i] = calc_d(mesh, i)

        for i in prange(nvertices, nogil=True):
            mesh.vertices[i, 0] += weights[i]*m*D[i].x;
            mesh.vertices[i, 1] += weights[i]*m*D[i].y;
            mesh.vertices[i, 2] += weights[i]*m*D[i].z;


def ca_smoothing(Mesh mesh, double T, double tmax, double bmin, int n_iters):
    """
    This is a implementation of the paper "Context-aware mesh smoothing for
    biomedical applications". It can be used to smooth meshes generated by
    binary images to remove its staircase artifacts and keep the fine features.

    Params:
        mesh: Mesh
        T: Min angle (between vertex faces and stack_orientation) to consider a
           vertex a staircase artifact
        tmax: max distance the vertex must be to its nearest artifact vertex
              to considered to calculate the weight
        bmin: The minimum weight
        n_iters: Number of iterations.
    """
    cdef double[3] stack_orientation = [0.0, 0.0, 1.0]

    t0 = time.time()
    cdef vector[vertex_id_t]* vertices_staircase =  find_staircase_artifacts(mesh, stack_orientation, T)
    print("vertices staircase", time.time() - t0)

    t0 = time.time()
    cdef vector[weight_t]* weights = calc_artifacts_weight(mesh, deref(vertices_staircase), tmax, bmin)
    print("Weights", time.time() - t0)

    del vertices_staircase

    t0 = time.time()
    taubin_smooth(mesh, deref(weights), 0.5, -0.53, n_iters)
    print("taubin", time.time() - t0)

    del weights
