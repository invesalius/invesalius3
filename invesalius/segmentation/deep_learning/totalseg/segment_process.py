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

import numpy as np

import invesalius.data.slice_ as slc
from invesalius.segmentation.deep_learning.segment import SegmentProcess
from invesalius.utils import new_name_by_pattern

logger = logging.getLogger(__name__)


class TotalSegProcess(SegmentProcess):
    def __init__(
        self,
        image,
        create_new_mask,
        backend,
        device_id,
        use_gpu,
        task,
        image_spacing,
        selected_class_ids=None,
    ):
        super().__init__(image, create_new_mask, backend, device_id, use_gpu)
        self.task = task
        self.image_spacing = tuple(image_spacing)
        self.selected_class_ids = selected_class_ids

    def _run_segmentation(self):
        # Lazy imports keep parent-process startup light and let the dialog
        # surface a clear error if torch/onnxruntime is missing.
        from . import merge as _merge
        from .inference import load_model
        from .inference import run as run_inference
        from .preprocess import read_sidecar
        from .weights import get_model_path, get_sidecar_path

        image = np.memmap(
            self._image_filename,
            dtype=self._image_dtype,
            shape=self._image_shape,
            mode="r",
        )
        prob_array = np.memmap(
            self._prob_array_filename,
            dtype=np.float32,
            shape=self._image_shape,
            mode="r+",
        )
        comm_array = np.memmap(self._comm_array_filename, dtype=np.float32, shape=(1,), mode="r+")

        # Network util reports 0..100; normalise into comm_array's 0..1 space.
        def dl_cb(pct):
            comm_array[0] = float(pct) / 100.0

        parts = (
            _merge.MULTIPART_TASKS[self.task]["parts"]
            if _merge.is_multipart(self.task)
            else [self.task]
        )

        sidecars = {p: read_sidecar(get_sidecar_path(p, progress_callback=dl_cb)) for p in parts}
        weight_paths = {p: get_model_path(p, self.backend, progress_callback=dl_cb) for p in parts}
        comm_array[0] = 0.0

        # InVesalius matrix is ZYX; Slice().spacing is XYZ. Inference engine
        # works in ZYX, so reverse spacing and pass volume directly.
        volume_zyx = np.ascontiguousarray(image, dtype=np.float32)
        spacing_zyx = np.array(self.image_spacing[::-1], dtype=np.float32)

        preds = {}
        n = len(parts)
        for i, part in enumerate(parts):
            handle = load_model(
                weight_paths[part],
                backend=self.backend,
                use_gpu=self.use_gpu,
                device_id=self.device_id,
            )
            sidecar = sidecars[part]
            modality = sidecar.get("modality", "CT").lower()

            def cb(f, idx=i, n_parts=n):
                comm_array[0] = (idx + f) / n_parts

            preds[part] = run_inference(
                volume_zyx,
                spacing_zyx,
                sidecar,
                handle,
                modality=modality,
                progress_callback=cb,
                output_layout="zyx",
            )

        unified = (
            _merge.merge_label_maps(preds, self.task)
            if _merge.is_multipart(self.task)
            else preds[parts[0]]
        )
        prob_array[:] = unified.astype(np.float32)
        prob_array.flush()
        comm_array[0] = np.inf

    def apply_segment_threshold(self, threshold=None):
        # threshold ignored — totalseg produces label maps, not probabilities.
        # Selected class IDs (from the dialog) are unioned into one binary mask.
        labels = self._probability_array.astype(np.uint8)
        ids = self.selected_class_ids
        if ids is None:
            ids = sorted(int(i) for i in np.unique(labels) if int(i) != 0)

        mask_data = np.zeros_like(labels, dtype=np.uint8)
        for cid in ids:
            mask_data[labels == int(cid)] = 255

        if self.create_new_mask:
            if self.mask is None:
                name = new_name_by_pattern(f"totalseg_{self.task}")
                self.mask = slc.Slice().create_new_mask(
                    name=name,
                    derived_from=getattr(slc.Slice(), "current_image_label", "Original"),
                )
        else:
            self.mask = slc.Slice().current_mask
            if self.mask is None:
                name = new_name_by_pattern(f"totalseg_{self.task}")
                self.mask = slc.Slice().create_new_mask(
                    name=name,
                    derived_from=getattr(slc.Slice(), "current_image_label", "Original"),
                )

        self.mask.was_edited = True
        self.mask.matrix[1:, 1:, 1:] = mask_data
        self.mask.matrix[:, 0, 0] = 2
        self.mask.matrix[0, :, 0] = 2
        self.mask.matrix[0, 0, :] = 2
        self.mask.matrix.flush()
        self.mask.modified(True)
