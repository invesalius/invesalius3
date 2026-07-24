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

import logging
from functools import lru_cache

import numpy as np

from . import labels as _labels

logger = logging.getLogger(__name__)


# Multi-part tasks. Parts merged in listed order; later parts overwrite earlier ones in overlap. Matches TotalSegmentator CLI.
# target: sidecar whose labels define the unified namespace, parts remapped by name.
# target=None: concatenate part namespaces with cumulative offsets.
MULTIPART_TASKS: dict = {
    "ct_total_1_5mm": {
        "parts": ["ct_organs", "ct_vertebrae", "ct_cardiac", "ct_muscles", "ct_ribs"],
        "target": "ct_total_3mm",
    },
    "mri_total": {
        "parts": ["mri_organs", "mri_muscles"],
        "target": None,
    },
}


def is_multipart(task: str) -> bool:
    return task in MULTIPART_TASKS


@lru_cache(maxsize=8)
def _build_remaps(composite_task: str) -> dict:
    spec = MULTIPART_TASKS[composite_task]
    parts = spec["parts"]
    target_task = spec["target"]

    if target_task is not None:
        target_labels = _labels.get_labels(target_task)
        target_name_to_id = {name: idx for idx, name in target_labels.items()}

        remaps: dict = {}
        for part in parts:
            part_labels = _labels.get_labels(part)
            remap: dict = {}
            for local_id, name in part_labels.items():
                unified_id = target_name_to_id.get(name)
                if unified_id is None:
                    logger.warning(
                        f"Part '{part}' label '{name}' (id={local_id}) "
                        f"missing from unified namespace '{target_task}'. Dropped."
                    )
                    continue
                remap[local_id] = unified_id
            remaps[part] = remap
        return remaps

    # Concatenation: shift each part's IDs by the cumulative count of prior parts
    # so namespaces do not collide.
    remaps = {}
    offset = 0
    for part in parts:
        part_labels = _labels.get_labels(part)
        remaps[part] = {local_id: local_id + offset for local_id in part_labels}
        offset += max(part_labels.keys(), default=0)
    return remaps


@lru_cache(maxsize=8)
def get_unified_labels(composite_task: str) -> dict:
    if composite_task not in MULTIPART_TASKS:
        raise ValueError(f"Unknown composite task '{composite_task}'")

    spec = MULTIPART_TASKS[composite_task]
    if spec["target"] is not None:
        return _labels.get_labels(spec["target"])

    remaps = _build_remaps(composite_task)
    out: dict = {}
    for part in spec["parts"]:
        part_labels = _labels.get_labels(part)
        for local_id, name in part_labels.items():
            out[remaps[part][local_id]] = name
    return out


def _apply_remap(local: np.ndarray, remap: dict) -> np.ndarray:
    # LUT-based remap. Faster than np.vectorize and avoids per-voxel Python.
    if not remap:
        return np.zeros_like(local, dtype=np.uint8)
    max_local = max(remap.keys())
    lut = np.zeros(max(int(local.max()), max_local) + 1, dtype=np.uint8)
    for local_id, unified_id in remap.items():
        lut[local_id] = unified_id
    return lut[local]


def merge_label_maps(
    part_predictions: dict,
    composite_task: str,
) -> np.ndarray:
    if composite_task not in MULTIPART_TASKS:
        raise ValueError(f"Unknown composite task '{composite_task}'")

    spec = MULTIPART_TASKS[composite_task]
    expected = set(spec["parts"])
    got = set(part_predictions.keys())
    if got != expected:
        missing = expected - got
        extra = got - expected
        raise ValueError(
            f"Part mismatch for '{composite_task}'. missing={sorted(missing)} extra={sorted(extra)}"
        )

    parts = spec["parts"]
    shape = part_predictions[parts[0]].shape
    for name in parts:
        if part_predictions[name].shape != shape:
            raise ValueError(
                f"Shape mismatch: part '{name}' is {part_predictions[name].shape}, expected {shape}"
            )

    remaps = _build_remaps(composite_task)
    unified = np.zeros(shape, dtype=np.uint8)
    for part in parts:
        remapped = _apply_remap(part_predictions[part], remaps[part])
        mask = remapped > 0
        unified[mask] = remapped[mask]
    return unified
