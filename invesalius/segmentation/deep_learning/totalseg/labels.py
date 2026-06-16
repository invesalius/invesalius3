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

from .preprocess import read_sidecar
from .weights import get_sidecar_path

logger = logging.getLogger(__name__)


# Anatomical categories used to group classes in the segmentation UI.
# Names are matched first against the exact-name set, then against prefixes.
# Anything that matches neither falls into "Other".
CATEGORY_GROUPS: dict = {
    "Organs": {
        "names": {
            "spleen",
            "kidney_right",
            "kidney_left",
            "kidney_cyst_left",
            "kidney_cyst_right",
            "gallbladder",
            "liver",
            "stomach",
            "pancreas",
            "adrenal_gland_right",
            "adrenal_gland_left",
            "esophagus",
            "trachea",
            "thyroid_gland",
            "small_bowel",
            "duodenum",
            "colon",
            "urinary_bladder",
            "prostate",
            "brain",
            "spinal_cord",
        },
        "prefixes": ("lung_",),
    },
    "Bones": {
        "names": {
            "sacrum",
            "skull",
            "sternum",
            "costal_cartilages",
            "hip_left",
            "hip_right",
            "femur_left",
            "femur_right",
            "humerus_left",
            "humerus_right",
            "scapula_left",
            "scapula_right",
            "clavicula_left",
            "clavicula_right",
            # MRI models group all vertebrae as one class and add disc spaces.
            "vertebrae",
            "intervertebral_discs",
        },
        "prefixes": ("vertebrae_", "rib_"),
    },
    "Cardiac": {
        "names": {"heart"},
        "prefixes": ("heart_", "atrial_appendage_"),
    },
    "Vessels": {
        "names": {
            "aorta",
            "inferior_vena_cava",
            "superior_vena_cava",
            "portal_vein_and_splenic_vein",
            "pulmonary_vein",
            "brachiocephalic_trunk",
        },
        "prefixes": (
            "iliac_",
            "common_carotid_",
            "brachiocephalic_vein_",
            "subclavian_",
            "pulmonary_artery",
        ),
    },
    "Muscles": {
        "names": {"autochthon_left", "autochthon_right"},
        "prefixes": ("gluteus_", "iliopsoas_"),
    },
}

CATEGORY_ORDER: tuple = ("Organs", "Bones", "Cardiac", "Vessels", "Muscles", "Other")


def _categorize(label_name: str) -> str:
    for category, rules in CATEGORY_GROUPS.items():
        if label_name in rules["names"]:
            return category
        if any(label_name.startswith(p) for p in rules["prefixes"]):
            return category
    return "Other"


@lru_cache(maxsize=16)
def get_labels(task: str) -> dict:
    sidecar_path = get_sidecar_path(task)
    sidecar = read_sidecar(sidecar_path)

    raw = sidecar.get("labels")
    if not raw:
        raise ValueError(f"Sidecar for task '{task}' has no 'labels' field")

    # Sidecars store {name: id}. Background (id 0) is dropped and it is not a selectable structure.
    out: dict = {}
    for name, idx in raw.items():
        idx = int(idx)
        if idx == 0:
            continue
        out[idx] = name
    return out


def get_label_name(task: str, class_id: int) -> str:
    return get_labels(task).get(class_id, f"unknown_{class_id}")


def get_categories_for_task(task: str) -> dict:
    labels = get_labels(task)
    grouped: dict = {category: [] for category in CATEGORY_ORDER}
    for class_id, name in labels.items():
        grouped[_categorize(name)].append(class_id)

    for ids in grouped.values():
        ids.sort()
    return {c: ids for c, ids in grouped.items() if ids}
