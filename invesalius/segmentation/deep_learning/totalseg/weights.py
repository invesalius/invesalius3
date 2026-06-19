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
from collections.abc import Callable

from invesalius import inv_paths
from invesalius.net.utils import download_url_to_file

logger = logging.getLogger(__name__)


_BASE_URL = "https://raw.githubusercontent.com/invesalius/weights/main/total_segmentator"


TASK_REGISTRY: dict = {
    "ct_total_3mm": {
        "modality": "CT",
        "spacing_mm": 3.0,
        "jit": {
            "filename": "ct_total_3mm.jit",
            "url": f"{_BASE_URL}/ct_total_3mm.jit",
            "hash": "c590bbadeff5fd9fcc9c274c8e96bcb89ed510555ecd2bd418616b133583bd23",
        },
        "onnx": {
            "filename": "ct_total_3mm.onnx",
            "url": f"{_BASE_URL}/ct_total_3mm.onnx",
            "hash": "832223e3c7e4a662f6969a5f1cc4c4e587490875dc9be61961817757a4a214dc",
        },
        "sidecar": {
            "filename": "ct_total_3mm.json",
            "url": f"{_BASE_URL}/ct_total_3mm.json",
            "hash": None,
        },
    },
    "ct_organs": {
        "modality": "CT",
        "spacing_mm": 1.5,
        "jit": {
            "filename": "ct_organs.jit",
            "url": f"{_BASE_URL}/ct_organs.jit",
            "hash": "af71cd7ae306c3823666796f258520e265096a7890e0e78da063e00985f44727",
        },
        "onnx": {
            "filename": "ct_organs.onnx",
            "url": f"{_BASE_URL}/ct_organs.onnx",
            "hash": "265ef8572b56cfe3f5eec4fc4c45856aada856f975713eeba3e2f45f13738fa5",
        },
        "sidecar": {
            "filename": "ct_organs.json",
            "url": f"{_BASE_URL}/ct_organs.json",
            "hash": None,
        },
    },
    "ct_vertebrae": {
        "modality": "CT",
        "spacing_mm": 1.5,
        "jit": {
            "filename": "ct_vertebrae.jit",
            "url": f"{_BASE_URL}/ct_vertebrae.jit",
            "hash": "246c52390a946db68a1302d1805c944efb9dd81da9b1dabe41641e0e0b6480cd",
        },
        "onnx": {
            "filename": "ct_vertebrae.onnx",
            "url": f"{_BASE_URL}/ct_vertebrae.onnx",
            "hash": "fbcdfe168e8e5e1204128248d936069505caddd345b02472e2c99d33a60c9454",
        },
        "sidecar": {
            "filename": "ct_vertebrae.json",
            "url": f"{_BASE_URL}/ct_vertebrae.json",
            "hash": None,
        },
    },
    "ct_cardiac": {
        "modality": "CT",
        "spacing_mm": 1.5,
        "jit": {
            "filename": "ct_cardiac.jit",
            "url": f"{_BASE_URL}/ct_cardiac.jit",
            "hash": "a54ce8da6a8aec8ab216d3bab33d3ac72ea57a14f717efacfe8f5cce296053c9",
        },
        "onnx": {
            "filename": "ct_cardiac.onnx",
            "url": f"{_BASE_URL}/ct_cardiac.onnx",
            "hash": "57764f4fad73e37f5af92f89905583357977c489ed2ae31c1791c39ef667c84f",
        },
        "sidecar": {
            "filename": "ct_cardiac.json",
            "url": f"{_BASE_URL}/ct_cardiac.json",
            "hash": None,
        },
    },
    "ct_muscles": {
        "modality": "CT",
        "spacing_mm": 1.5,
        "jit": {
            "filename": "ct_muscles.jit",
            "url": f"{_BASE_URL}/ct_muscles.jit",
            "hash": "2532216ad2e2f8766c16d919f8d9ae9f7617fd35c4a8f6571f7eeeccca410866",
        },
        "onnx": {
            "filename": "ct_muscles.onnx",
            "url": f"{_BASE_URL}/ct_muscles.onnx",
            "hash": "7186d50d9a00500c66e5fe58722d617efc3d9d17d13da3c5c8931c7d0e02e565",
        },
        "sidecar": {
            "filename": "ct_muscles.json",
            "url": f"{_BASE_URL}/ct_muscles.json",
            "hash": None,
        },
    },
    "ct_ribs": {
        "modality": "CT",
        "spacing_mm": 1.5,
        "jit": {
            "filename": "ct_ribs.jit",
            "url": f"{_BASE_URL}/ct_ribs.jit",
            "hash": "aed6a647a69a9448c48ca506e6686a2d7b2be4534b8eda91e20cc2a262398479",
        },
        "onnx": {
            "filename": "ct_ribs.onnx",
            "url": f"{_BASE_URL}/ct_ribs.onnx",
            "hash": "91954fec5388aa64dbc019dc7f58a440588d5249557a7dcf08cf65970803612e",
        },
        "sidecar": {
            "filename": "ct_ribs.json",
            "url": f"{_BASE_URL}/ct_ribs.json",
            "hash": None,
        },
    },
    "mri_organs": {
        "modality": "MRI",
        "spacing_mm": 1.5,
        "jit": {
            "filename": "mri_organs.jit",
            "url": f"{_BASE_URL}/mri_organs.jit",
            "hash": "40c4369817d573f5149edcffbe1892077f8b7fe471896ec1968f84646ca63559",
        },
        "onnx": {
            "filename": "mri_organs.onnx",
            "url": f"{_BASE_URL}/mri_organs.onnx",
            "hash": "f732bbcff122df2407e479d8fec8a0d4d0f18489d12f6cd0167b8aef7ecef437",
        },
        "sidecar": {
            "filename": "mri_organs.json",
            "url": f"{_BASE_URL}/mri_organs.json",
            "hash": None,
        },
    },
    "mri_muscles": {
        "modality": "MRI",
        "spacing_mm": 1.5,
        "jit": {
            "filename": "mri_muscles.jit",
            "url": f"{_BASE_URL}/mri_muscles.jit",
            "hash": "f811cc59c9de4cba86ba72bef9bfb63db578af86bb5078358a3a20a4e2811c64",
        },
        "onnx": {
            "filename": "mri_muscles.onnx",
            "url": f"{_BASE_URL}/mri_muscles.onnx",
            "hash": "a956ffad0ba3c8a32c9cfe43d8553724d3b298e2aad26e1189da3d41481c8c05",
        },
        "sidecar": {
            "filename": "mri_muscles.json",
            "url": f"{_BASE_URL}/mri_muscles.json",
            "hash": None,
        },
    },
}


def _resolve(filename: str) -> tuple[bool, str]:
    sys_path = inv_paths.MODELS_DIR / "totalseg" / filename
    user_path = inv_paths.USER_DL_WEIGHTS / filename
    if sys_path.exists():
        return True, str(sys_path)
    if user_path.exists():
        return True, str(user_path)
    return False, str(user_path)


def get_model_path(
    task: str,
    backend: str = "jit",
    progress_callback: Callable[[float], None] | None = None,
) -> str:
    if task not in TASK_REGISTRY:
        raise ValueError(f"Unknown task '{task}'. Known: {list(TASK_REGISTRY)}")
    if backend not in ("jit", "onnx"):
        raise ValueError(f"Unknown backend '{backend}'. Use 'jit' or 'onnx'.")

    info = TASK_REGISTRY[task][backend]
    found, path = _resolve(info["filename"])
    if found:
        return path

    logger.info(f"Downloading {info['filename']} from {info['url']}")
    download_url_to_file(info["url"], path, info["hash"], progress_callback)
    return path


def get_sidecar_path(
    task: str,
    progress_callback: Callable[[float], None] | None = None,
) -> str:
    if task not in TASK_REGISTRY:
        raise ValueError(f"Unknown task '{task}'. Known: {list(TASK_REGISTRY)}")

    info = TASK_REGISTRY[task]["sidecar"]
    found, path = _resolve(info["filename"])
    if found:
        return path

    logger.info(f"Downloading {info['filename']} from {info['url']}")
    download_url_to_file(info["url"], path, info["hash"], progress_callback)
    return path
