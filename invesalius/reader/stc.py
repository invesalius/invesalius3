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

"""Read scalar STC source time courses without an MNE dependency.

The big-endian layout is tmin/dt (float32 milliseconds), vertex count
(uint32), vertex IDs (uint32), frame count (uint32), then float32 values
in frame-major order. Reference: mne-python/mne/source_estimate.py::_read_stc.
"""

from dataclasses import dataclass
from pathlib import Path
from struct import unpack

import numpy as np

from invesalius.data.time_series import TimeAxis


@dataclass
class STC:
    axis: TimeAxis
    vertices: np.ndarray
    values: np.ndarray

    def read_frame(self, frame_index):
        return self.values[self.axis.check_index(frame_index)]


def read_stc(filename):
    """Validate the header and map values read-only, loading one frame at a time."""
    with Path(filename).open("rb") as stream:
        stream.seek(0, 2)
        size = stream.tell()
        stream.seek(0)
        if size < 16:
            raise ValueError("Truncated STC header.")
        t0, dt, n_vertices = unpack(">ffI", stream.read(12))
        offset = 16 + 4 * n_vertices
        if offset > size:
            raise ValueError("Truncated STC vertex list.")
        vertices = np.fromfile(stream, dtype=">u4", count=n_vertices)
        n_frames = unpack(">I", stream.read(4))[0]
        axis = TimeAxis(t0 / 1000, dt / 1000, n_frames)
        if size != offset + 4 * n_vertices * n_frames:
            raise ValueError("STC file size does not match its vertex and frame counts.")
        if len(np.unique(vertices)) != n_vertices:
            raise ValueError("STC vertex IDs must be unique.")
        vertices.flags.writeable = False
        values = (
            np.memmap(stream, dtype=">f4", mode="r", offset=offset, shape=(n_frames, n_vertices))
            if n_vertices
            else np.empty((n_frames, 0), dtype=">f4")
        )
        values.flags.writeable = False
    return STC(axis, vertices, values)


def read_stc_pair(filename):
    """Load the matching lh/rh files and require a common time axis."""
    filename = Path(filename)
    if not filename.name.endswith(("-lh.stc", "-rh.stc")):
        raise ValueError("Select a cortical STC file ending in '-lh.stc' or '-rh.stc'.")
    stem = filename.name[:-7]
    pair = tuple(read_stc(filename.with_name(f"{stem}-{side}.stc")) for side in ("lh", "rh"))
    left, right = pair
    if left.axis != right.axis:
        raise ValueError("The STC hemispheres have different time axes.")
    if not len(left.vertices) + len(right.vertices):
        raise ValueError("The STC pair does not contain any sources.")
    return pair
