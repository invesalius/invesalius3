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

"""Load cortical source series and their registered geometry from a JSON config."""

import json
from dataclasses import dataclass
from pathlib import Path

import nibabel as nib
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

from invesalius.reader.stc import STC, read_stc_pair


@dataclass
class CorticalSourceSeries:
    hemispheres: tuple[STC, STC]
    points: np.ndarray
    triangles: np.ndarray
    vertex_sources: np.ndarray
    scalar_range: tuple[float, float]
    name: str
    unit: str

    @property
    def axis(self):
        return self.hemispheres[0].axis

    def read_frame(self, frame_index):
        """Return the sampled sources, in lh then rh order, without spatial resampling."""
        return np.concatenate([stc.read_frame(frame_index) for stc in self.hemispheres])


def _affine(matrix):
    matrix = np.asarray(matrix, dtype=float)
    if (
        matrix.shape != (4, 4)
        or not np.isfinite(matrix).all()
        or not np.allclose(matrix[3], [0, 0, 0, 1])
        or np.linalg.matrix_rank(matrix[:3, :3]) != 3
    ):
        raise ValueError("Registration must be a finite, invertible 4x4 positional affine.")
    return matrix


def _vertex_sources(points, triangles, source_vertices):
    """Assign the nearest sampled source along mesh edges, never across a sulcus."""
    edges = np.concatenate([triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]]])
    edges = np.unique(np.sort(edges, axis=1), axis=0)
    lengths = np.linalg.norm(points[edges[:, 0]] - points[edges[:, 1]], axis=1)
    graph = csr_matrix(
        (np.tile(lengths, 2), (edges.T.ravel(), edges[:, ::-1].T.ravel())),
        shape=(len(points), len(points)),
    )
    _, _, nearest = dijkstra(
        graph, indices=source_vertices, min_only=True, return_predecessors=True
    )
    rows = np.full(len(points), -1, dtype=np.int64)
    rows[source_vertices] = np.arange(len(source_vertices))
    mapped = nearest >= 0
    result = np.full(len(points), -1, dtype=np.int64)
    result[mapped] = rows[nearest[mapped]]
    return result


def _scalar_range(hemispheres):
    minimum, maximum = float("inf"), float("-inf")
    for stc in hemispheres:
        if not len(stc.vertices):
            continue
        frames_per_chunk = max(1, 1_000_000 // len(stc.vertices))
        for start in range(0, stc.axis.n_frames, frames_per_chunk):
            chunk = stc.values[start : start + frames_per_chunk]
            if not np.isfinite(chunk).all():
                raise ValueError("STC source values must be finite.")
            minimum = min(minimum, float(chunk.min()))
            maximum = max(maximum, float(chunk.max()))
    return minimum, maximum


def read_source_config(filename):
    """Validate the complete import before any project or viewer state is changed.

    The MRI must be the FreeSurfer MGH/MGZ reference for these surfaces.
    scanner_ras_to_project_ras explicitly registers its scanner coordinates
    to those of the project's anatomical image; all spatial units are mm.
    """
    filename = Path(filename)
    with filename.open(encoding="utf-8") as stream:
        config = json.load(stream)
    required = ("stc", "lh_surface", "rh_surface", "mri", "unit", "scanner_ras_to_project_ras")
    if not isinstance(config, dict) or any(key not in config for key in required):
        raise ValueError(f"Source configuration requires: {', '.join(required)}.")
    for key in ("stc", "lh_surface", "rh_surface", "mri", "unit"):
        if not isinstance(config[key], str) or not config[key].strip():
            raise ValueError(f"Source configuration '{key}' must be a nonempty string.")
    name = config.get("name", Path(config["stc"]).name[:-7])
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Source name must be a nonempty string.")
    registration = _affine(config["scanner_ras_to_project_ras"])
    hemispheres = read_stc_pair(filename.parent / config["stc"])
    mri = nib.load(filename.parent / config["mri"])
    if not isinstance(mri, nib.freesurfer.mghformat.MGHImage):
        raise ValueError("Source MRI reference must be a FreeSurfer MGH or MGZ image.")
    surface_to_project = _affine(
        registration @ _affine(mri.affine) @ np.linalg.inv(_affine(mri.header.get_vox2ras_tkr()))
    )
    points, triangles, source_vertices = [], [], []
    offset = 0
    for side, stc in zip(("lh", "rh"), hemispheres):
        vertices, faces = nib.freesurfer.read_geometry(filename.parent / config[f"{side}_surface"])
        if (
            vertices.ndim != 2
            or vertices.shape[1] != 3
            or not len(vertices)
            or not np.isfinite(vertices).all()
            or faces.ndim != 2
            or faces.shape[1] != 3
            or not len(faces)
            or faces.min() < 0
            or faces.max() >= len(vertices)
        ):
            raise ValueError(f"Invalid {side} cortical surface geometry.")
        if len(stc.vertices) and stc.vertices.max() >= len(vertices):
            raise ValueError(f"STC vertex IDs exceed the {side} surface vertex count.")
        points.append(vertices)
        triangles.append(faces.astype(np.int64) + offset)
        source_vertices.append(stc.vertices.astype(np.int64) + offset)
        offset += len(vertices)
    points = np.concatenate(points)
    triangles = np.concatenate(triangles)
    source_vertices = np.concatenate(source_vertices)
    scalar_range = _scalar_range(hemispheres)
    vertex_sources = _vertex_sources(points, triangles, source_vertices)
    registered_points = nib.affines.apply_affine(surface_to_project, points)
    if not np.isfinite(registered_points).all():
        raise ValueError("Registered source geometry must be finite.")
    return CorticalSourceSeries(
        hemispheres,
        registered_points,
        triangles,
        vertex_sources,
        scalar_range,
        name,
        config["unit"],
    )
