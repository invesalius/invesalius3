# --------------------------------------------------------------------------
# Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
# Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
# Homepage:     http://www.softwarepublico.gov.br
# Contact:      invesalius@cti.gov.br
# License:      GNU - GPL 2 (LICENSE.txt/LICENCA.txt)
# --------------------------------------------------------------------------
#    Este programa e software livre; voce pode redistribui-lo e/ou
#    modifica-lo sob os termos da Licenca Publica Geral GNU, conforme
#    publicada pela Free Software Foundation; de acordo com a versao 2
#    da Licenca.
#
#    Este programa eh distribuido na expectativa de ser util, mas SEM
#    QUALQUER GARANTIA; sem mesmo a garantia implicita de
#    COMERCIALIZACAO ou de ADEQUACAO A QUALQUER PROPOSITO EM
#    PARTICULAR. Consulte a Licenca Publica Geral GNU para obter mais
#    detalhes.
# --------------------------------------------------------------------------

import os
import re

import numpy as np
from vtkmodules.util import numpy_support
from vtkmodules.vtkCommonCore import VTK_UNSIGNED_CHAR
from vtkmodules.vtkCommonDataModel import vtkPlane, vtkPolyData
from vtkmodules.vtkCommonTransforms import vtkTransform
from vtkmodules.vtkFiltersCore import vtkCutter
from vtkmodules.vtkFiltersGeneral import vtkTransformPolyDataFilter
from vtkmodules.vtkIOLegacy import vtkPolyDataReader
from vtkmodules.vtkIOXML import vtkXMLPolyDataReader

import invesalius.constants as const
import invesalius.data.slice_ as sl

_EFIELD_ARRAY_CANDIDATES = ("magnE", "normE", "magnJ", "magn", "E", "scalars")

# Adjustable in the panel
EFIELD_SAMPLING_MAX_DISTANCE = 6.0

COLORS_ARRAY_NAME = "Colors"


def ReadEfieldSurface(path):
    polydata = _ReadEfieldPolyData(path)

    point_data = polydata.GetPointData()
    scalars = _SelectEfieldArray(point_data)
    vtk_vectors = point_data.GetVectors()
    vectors = numpy_support.vtk_to_numpy(vtk_vectors) if vtk_vectors is not None else None

    if scalars is not None:
        norms = numpy_support.vtk_to_numpy(scalars)
        if norms.ndim > 1:
            norms = np.linalg.norm(norms, axis=1)
    elif vectors is not None:
        norms = np.linalg.norm(vectors, axis=1)
    else:
        raise ValueError(
            "the surface has no point data to colour by (expected the E-field "
            "magnitude, e.g. 'magnE')"
        )

    return polydata, np.asarray(norms, dtype=float), vectors


def _ReadEfieldPolyData(path):
    extension = os.path.splitext(path)[1].lower()
    if extension == ".vtp":
        reader = vtkXMLPolyDataReader()
    elif extension == ".vtk":
        reader = vtkPolyDataReader()
        reader.ReadAllScalarsOn()
        reader.ReadAllVectorsOn()
    else:
        raise ValueError(
            f"unsupported E-field surface format '{extension}'. The SimNIBS server "
            "must send a VTK surface (.vtk/.vtp), not the raw .msh."
        )
    reader.SetFileName(path)
    reader.Update()

    _affine, affine_vtk, _img_shift = sl.Slice().get_world_to_invesalius_vtk_affine(inverse=False)

    transform = vtkTransform()
    transform.PostMultiply()
    transform.Concatenate(affine_vtk)

    transform_filter = vtkTransformPolyDataFilter()
    transform_filter.SetTransform(transform)
    transform_filter.SetInputData(reader.GetOutput())
    transform_filter.Update()

    polydata = transform_filter.GetOutput()
    if polydata is None or polydata.GetNumberOfPoints() == 0:
        raise ValueError("the E-field surface file is empty or could not be read")
    return polydata


def ShareGeometry(polydata):
    """A polydata sharing points and cells with its own point data."""
    shared = vtkPolyData()
    shared.SetPoints(polydata.GetPoints())
    shared.SetVerts(polydata.GetVerts())
    shared.SetLines(polydata.GetLines())
    shared.SetPolys(polydata.GetPolys())
    shared.SetStrips(polydata.GetStrips())

    normals = polydata.GetPointData().GetNormals()
    if normals is not None:
        shared.GetPointData().SetNormals(normals)
    return shared


def SampleEfieldOntoSurface(
    source_polydata, norms, target_polydata, max_distance=EFIELD_SAMPLING_MAX_DISTANCE
):
    """Carry the field values of the E-field mesh over to another surface."""
    from scipy.spatial import cKDTree

    source_points = numpy_support.vtk_to_numpy(source_polydata.GetPoints().GetData())
    target_points = numpy_support.vtk_to_numpy(target_polydata.GetPoints().GetData())
    if not len(source_points) or not len(target_points):
        return np.empty(0), [], np.empty(0, dtype=int), 0.0, float("inf")

    distances, indices = cKDTree(source_points).query(target_points, k=1)
    within = distances <= max_distance

    source_ids = indices[within]
    values = np.asarray(norms, dtype=float)[source_ids]
    point_ids = np.flatnonzero(within).tolist()
    coverage = float(np.count_nonzero(within)) / len(target_points)
    return values, point_ids, source_ids, coverage, float(np.min(distances))


def BuildPointTree(polydata):
    """A nearest-point index over the mesh, built once and reused across surfaces"""
    from scipy.spatial import cKDTree

    return cKDTree(numpy_support.vtk_to_numpy(polydata.GetPoints().GetData()))


def EstimateCoverage(
    tree, target_polydata, max_distance=EFIELD_SAMPLING_MAX_DISTANCE, samples=2000
):
    """Share of a surface the field reaches, judged on a thinned set of its points"""
    points = numpy_support.vtk_to_numpy(target_polydata.GetPoints().GetData())
    if not len(points):
        return 0.0
    if len(points) > samples:
        points = points[:: len(points) // samples + 1]
    distances, _ = tree.query(points, k=1)
    return float(np.count_nonzero(distances <= max_distance)) / len(points)


def IsDefaultTarget(name):
    """True for a surface name the field belongs on, to break ties between the ones it reaches"""
    words = set(re.split(r"[^a-z0-9]+", name.lower()))
    return bool(words & {"gm", "gray", "grey", "cortex"})


def ColorsFromLUT(values, lut):
    """Look `values` up in `lut`, as an (N, 3) uint8 array."""
    table = numpy_support.vtk_to_numpy(lut.GetTable()).reshape(-1, 4)[:, :3]
    minimum, maximum = lut.GetTableRange()
    values = np.asarray(values, dtype=float)
    if maximum <= minimum:
        indexes = np.zeros(len(values), dtype=int)
    else:
        scaled = (values - minimum) / (maximum - minimum) * len(table)
        indexes = np.clip(scaled.astype(int), 0, len(table) - 1)
    return table[indexes].astype(np.uint8)


def BuildColorArray(number_of_points, point_ids, values, lut, base_colour=None):
    """A per-point colour array for a surface, with the unsampled points left plain."""
    base = np.asarray(const.CORTEX_COLOR if base_colour is None else base_colour, dtype=np.uint8)
    rgb = np.tile(base, (number_of_points, 1))
    if len(point_ids):
        rgb[np.asarray(point_ids, dtype=int)] = ColorsFromLUT(values, lut)

    colors = numpy_support.numpy_to_vtk(
        np.ascontiguousarray(rgb), deep=True, array_type=VTK_UNSIGNED_CHAR
    )
    colors.SetNumberOfComponents(3)
    colors.SetName(COLORS_ARRAY_NAME)
    return colors


def CreateCutter(polydata):
    plane = vtkPlane()
    cutter = vtkCutter()
    cutter.SetCutFunction(plane)
    cutter.SetInputData(polydata)
    return cutter, plane


def _SelectEfieldArray(point_data):
    active = point_data.GetScalars()
    if active is not None:
        return active

    for name in _EFIELD_ARRAY_CANDIDATES:
        array = point_data.GetArray(name)
        if array is not None:
            return array

    for i in range(point_data.GetNumberOfArrays()):
        array = point_data.GetArray(i)
        if array is not None and array.GetNumberOfComponents() == 1:
            return array

    return None
