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
import os
import tempfile
import time

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
        selected_class_names=None,
    ):
        super().__init__(image, create_new_mask, backend, device_id, use_gpu)
        self.task = task
        self.image_spacing = tuple(image_spacing)
        self.selected_class_ids = selected_class_ids
        self.selected_class_names = selected_class_names or {}
        self.masks_created = 0

        # Status text channel; dialog polls via get_status().
        fd, self._status_filename = tempfile.mkstemp(suffix=".txt", prefix="totalseg_status_")
        os.close(fd)

    def _set_status(self, msg: str) -> None:
        try:
            with open(self._status_filename, "w", encoding="utf-8") as f:
                f.write(msg)
        except OSError:
            pass

    def get_status(self) -> str:
        try:
            with open(self._status_filename, encoding="utf-8") as f:
                return f.read()
        except OSError:
            return ""

    def _run_segmentation(self):
        # Lazy imports: torch/onnx aren't needed until inference actually runs.
        from . import merge as _merge
        from .inference import load_model
        from .inference import run as run_inference
        from .preprocess import read_sidecar
        from .weights import get_model_path, get_sidecar_path

        # print() (not logger) so messages reach the terminal from the spawn subprocess on Windows.
        print(f"[totalseg-child] START task={self.task} backend={self.backend}", flush=True)
        print(f"[totalseg-child] prob_array file: {self._prob_array_filename}", flush=True)

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

        # Network util reports 0..100; normalise to 0..1.
        def dl_cb(pct):
            comm_array[0] = float(pct) / 100.0

        parts = (
            _merge.MULTIPART_TASKS[self.task]["parts"]
            if _merge.is_multipart(self.task)
            else [self.task]
        )
        print(f"[totalseg-child] parts to run: {parts}", flush=True)

        sidecars = {}
        weight_paths = {}
        n_parts = len(parts)
        for pi, p in enumerate(parts, start=1):
            print(f"[totalseg-child] resolving sidecar for {p}...", flush=True)
            self._set_status(f"Downloading sidecar for {p} ({pi}/{n_parts})")
            sc_path = get_sidecar_path(p, progress_callback=dl_cb)
            sidecars[p] = read_sidecar(sc_path)
            print(f"[totalseg-child]   -> {sc_path}", flush=True)

            print(f"[totalseg-child] resolving weights for {p}...", flush=True)
            self._set_status(f"Downloading {p} weights ({pi}/{n_parts})")
            weight_paths[p] = get_model_path(p, self.backend, progress_callback=dl_cb)
            print(f"[totalseg-child]   -> {weight_paths[p]}", flush=True)
        comm_array[0] = 0.0

        # InVesalius matrix is ZYX, spacing is XYZ. Inference wants ZYX for both.
        volume_zyx = np.ascontiguousarray(image, dtype=np.float32)
        spacing_zyx = np.array(self.image_spacing[::-1], dtype=np.float32)

        preds = {}
        print(
            f"[totalseg-child] requested backend={self.backend} "
            f"use_gpu={self.use_gpu} device_id={self.device_id}",
            flush=True,
        )
        for i, part in enumerate(parts):
            print(f"[totalseg-child] [{i + 1}/{n_parts}] loading model: {part}", flush=True)
            self._set_status(f"Loading model {part} ({i + 1}/{n_parts})")
            handle = load_model(
                weight_paths[part],
                backend=self.backend,
                use_gpu=self.use_gpu,
                device_id=self.device_id,
            )
            # Torch can silently fall back to CPU on load; log the actual device.
            if handle["type"] == "jit":
                print(
                    f"[totalseg-child] [{i + 1}/{n_parts}] model on device: {handle['device']}",
                    flush=True,
                )
            sidecar = sidecars[part]
            modality = sidecar.get("modality", "CT").lower()

            def cb(f, idx=i, total=n_parts):
                comm_array[0] = (idx + f) / total

            print(
                f"[totalseg-child] [{i + 1}/{n_parts}] running inference on {part}...",
                flush=True,
            )
            self._set_status(f"Running inference on {part} ({i + 1}/{n_parts})")
            t_inf = time.time()
            preds[part] = run_inference(
                volume_zyx,
                spacing_zyx,
                sidecar,
                handle,
                modality=modality,
                progress_callback=cb,
                output_layout="zyx",
            )
            elapsed = time.time() - t_inf
            part_unique = np.unique(preds[part])
            print(
                f"[totalseg-child] [{i + 1}/{n_parts}] {part} done in {elapsed:.1f}s. "
                f"pred shape={preds[part].shape} unique={sorted(part_unique.tolist())[:15]}",
                flush=True,
            )

        if _merge.is_multipart(self.task):
            self._set_status("Merging part predictions")
            unified = _merge.merge_label_maps(preds, self.task)
        else:
            unified = preds[parts[0]]

        self._set_status("Writing result")

        u = np.unique(unified)
        print(
            f"[totalseg-child] unified shape={unified.shape} dtype={unified.dtype} "
            f"unique IDs: {sorted(u.tolist())[:20]}"
            + (f" (+{len(u) - 20} more)" if len(u) > 20 else ""),
            flush=True,
        )
        print(f"[totalseg-child] prob_array shape={prob_array.shape} WRITING...", flush=True)

        prob_array[:] = unified.astype(np.float32)
        prob_array.flush()
        print("[totalseg-child] write + flush done. Signalling completion.", flush=True)
        comm_array[0] = np.inf

    def apply_segment_threshold(self, threshold=None):
        # Threshold arg ignored: totalseg outputs label maps, not probabilities.
        # One mask per selected structure so each is toggleable independently.
        # Re-open the memmap: parent's cached view can be stale on Windows.
        fresh = np.memmap(
            self._prob_array_filename,
            dtype=np.float32,
            shape=self._image_shape,
            mode="r",
        )
        labels = np.asarray(fresh).astype(np.uint8)
        del fresh

        unique_ids = sorted(np.unique(labels).tolist())
        print(
            f"[totalseg-parent] read prob_array file: {self._prob_array_filename}",
            flush=True,
        )
        print(
            f"[totalseg-parent] shape={self._image_shape}, "
            f"unique class ids in labels: {unique_ids[:20]}"
            + (f" (+{len(unique_ids) - 20} more)" if len(unique_ids) > 20 else ""),
            flush=True,
        )

        ids = self.selected_class_ids
        if ids is None:
            ids = sorted(int(i) for i in unique_ids if int(i) != 0)

        derived = getattr(slc.Slice(), "current_image_label", "Original")
        self.masks_created = 0
        last_mask = None

        for cid in ids:
            structure = self.selected_class_names.get(int(cid), f"class_{int(cid)}")
            mask_data = (labels == int(cid)).astype(np.uint8) * 255
            voxel_count = int(mask_data.sum() // 255)

            # Skip empty structures (outside FOV or model missed).
            if voxel_count == 0:
                print(
                    f"[totalseg-parent] skipping {structure} (class {cid}): 0 voxels",
                    flush=True,
                )
                continue

            mask_name = new_name_by_pattern(structure)
            mask = slc.Slice().create_new_mask(name=mask_name, derived_from=derived)
            print(
                f"[totalseg-parent] {structure} (class {cid}): {voxel_count} voxels -> {mask_name}",
                flush=True,
            )
            mask.was_edited = True
            mask.matrix[1:, 1:, 1:] = mask_data
            # Border = 2 marks slices as AI-edited so the lazy viewer doesn't overwrite them.
            mask.matrix[:, 0, 0] = 2
            mask.matrix[0, :, 0] = 2
            mask.matrix[0, 0, :] = 2
            mask.matrix.flush()
            mask.modified(True)

            last_mask = mask
            self.masks_created += 1

        # Keep last mask on self.mask for downstream compatibility.
        self.mask = last_mask

    def __del__(self):
        try:
            if hasattr(self, "_status_filename") and os.path.exists(self._status_filename):
                os.remove(self._status_filename)
        except OSError:
            pass
        try:
            super().__del__()
        except Exception:  # noqa: BLE001
            pass
