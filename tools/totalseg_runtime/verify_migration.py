"""Verify the migrated invesalius/.../totalseg/ produces the same Dice as the
tools/totalseg_runtime/ version. End-to-end run on a CT, compare to the
reference TotalSegmentator CLI output.

Supports both single-task and composite tasks:
  Single tasks (from TASK_REGISTRY): ct_total_3mm, ct_organs, ct_vertebrae, ...
  Composite tasks (from MULTIPART_TASKS): ct_total_1_5mm, mri_total
    Composite runs each part in sequence and merges into the unified namespace,
    same code path as TotalSegProcess uses inside the GUI.

Two modes via --layout:
  --layout xyz (default): standalone path used by nibabel callers. Volume comes
    in as XYZ, run() transposes to ZYX internally, returns XYZ.
  --layout zyx: wrapper path used by TotalSegProcess inside InVesalius. Volume
    is passed in ZYX (matching Slice matrix), spacing is reversed to ZYX,
    run() skips the final transpose via output_layout="zyx".

Both modes should produce the same Dice against the reference.

Usage (single task):
    python tools/totalseg_runtime/verify_migration.py \
        --ct <ct.nii.gz> --task ct_total_3mm --backend jit \
        --reference <ref_multilabel.nii.gz> --layout xyz

Usage (composite task on GPU):
    python tools/totalseg_runtime/verify_migration.py \
        --ct <ct.nii.gz> --task ct_total_1_5mm --backend jit --gpu \
        --reference <ref_multilabel.nii.gz> --layout zyx
"""

import argparse
import time
from pathlib import Path

import nibabel as nib
import numpy as np

from invesalius.segmentation.deep_learning.totalseg.inference import load_model, run
from invesalius.segmentation.deep_learning.totalseg.merge import (
    MULTIPART_TASKS,
    is_multipart,
    merge_label_maps,
)
from invesalius.segmentation.deep_learning.totalseg.preprocess import load_nifti, read_sidecar
from invesalius.segmentation.deep_learning.totalseg.weights import get_model_path, get_sidecar_path


def dice_per_class(pred: np.ndarray, ref: np.ndarray) -> dict:
    classes = sorted(set(np.unique(pred).tolist()) | set(np.unique(ref).tolist()))
    out = {}
    for c in classes:
        if c == 0:
            continue
        p = pred == c
        r = ref == c
        ps, rs = int(p.sum()), int(r.sum())
        if ps + rs == 0:
            continue
        inter = int((p & r).sum())
        out[int(c)] = 2.0 * inter / (ps + rs)
    return out


def _download_progress(kind: str):
    def cb(pct: float):
        print(f"  {kind} download: {pct:5.1f}%", end="\r", flush=True)

    return cb


def _run_part(volume, spacing, sidecar, handle, output_layout, part_name):
    print(f"\nRunning inference [{part_name}] (output_layout='{output_layout}')...")
    t = time.perf_counter()
    pred = run(
        volume,
        spacing,
        sidecar,
        handle,
        modality=sidecar.get("modality", "CT").lower(),
        output_layout=output_layout,
    )
    print(f"  time: {time.perf_counter() - t:.2f}s  shape: {pred.shape}")
    return pred


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ct", required=True, type=Path)
    parser.add_argument(
        "--task",
        default="ct_total_3mm",
        help="Task from TASK_REGISTRY (single) or MULTIPART_TASKS (composite).",
    )
    parser.add_argument("--backend", default="jit", choices=("jit", "onnx"))
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument(
        "--layout",
        default="xyz",
        choices=("xyz", "zyx"),
        help="xyz: standalone path (default). zyx: wrapper path used by TotalSegProcess.",
    )
    parser.add_argument(
        "--gpu",
        action="store_true",
        help="Run inference on CUDA (default: CPU). Recommended for composite tasks.",
    )
    parser.add_argument("--device", default="cuda:0", help="Device id when --gpu is used.")
    parser.add_argument("--save-pred", type=Path, default=None)
    args = parser.parse_args()

    t_start = time.perf_counter()
    parts = MULTIPART_TASKS[args.task]["parts"] if is_multipart(args.task) else [args.task]

    print(f"Task:             {args.task}")
    print(f"Backend:          {args.backend}")
    print(f"Layout:           {args.layout}")
    print(f"GPU:              {args.gpu} ({args.device if args.gpu else 'cpu'})")
    print(f"Parts to run:     {parts}")

    print("\nResolving sidecars + weights...")
    sidecars = {}
    weight_paths = {}
    for p in parts:
        sidecars[p] = read_sidecar(
            str(get_sidecar_path(p, progress_callback=_download_progress(f"sidecar/{p}")))
        )
        weight_paths[p] = get_model_path(
            p, args.backend, progress_callback=_download_progress(f"weights/{p}")
        )
    print()  # flush the download progress lines

    print(f"Loading CT:       {args.ct}")
    volume_zyx, spacing_zyx = load_nifti(str(args.ct))
    print(f"  shape (ZYX): {volume_zyx.shape}, spacing: {spacing_zyx.tolist()}")

    output_layout = "zyx" if args.layout == "zyx" else "input"

    preds = {}
    for p in parts:
        handle = load_model(
            weight_paths[p],
            backend=args.backend,
            use_gpu=args.gpu,
            device_id=args.device,
        )
        preds[p] = _run_part(volume_zyx, spacing_zyx, sidecars[p], handle, output_layout, p)

    if is_multipart(args.task):
        print("\nMerging part predictions...")
        pred = merge_label_maps(preds, args.task)
    else:
        pred = preds[parts[0]]

    ref_expected_layout = "zyx" if args.layout == "zyx" else "xyz"
    print(f"\nFinal pred shape: {pred.shape}")

    if args.save_pred is not None:
        # pred was produced from the canonicalized CT (load_nifti calls
        # as_closest_canonical); stamp with the canonical affine so data and
        # affine agree. Using the raw ct.affine here would misalign whenever
        # the source CT isn't already RAS+.
        pred_xyz = pred.transpose(2, 1, 0) if args.layout == "zyx" else pred
        ct_canon = nib.as_closest_canonical(nib.load(str(args.ct)))
        out_img = nib.Nifti1Image(pred_xyz.astype(np.uint8), ct_canon.affine)
        nib.save(out_img, str(args.save_pred))
        print(f"Saved prediction to: {args.save_pred}")

    print(f"\nLoading reference: {args.reference}")
    # load_nifti canonicalises the CT (RAS+); apply the same to the reference
    # so voxels line up when the source was stored in a non-canonical orientation.
    ref_img = nib.as_closest_canonical(nib.load(str(args.reference)))
    ref = ref_img.get_fdata().astype(np.int32)
    if ref_expected_layout == "zyx":
        ref = ref.transpose(2, 1, 0)
    print(f"Ref shape: {ref.shape}")

    if pred.shape != ref.shape:
        print(f"ERROR: shape mismatch. pred={pred.shape} ref={ref.shape}")
        _print_total(t_start)
        return

    dices = dice_per_class(pred, ref)
    values = np.array(list(dices.values()))

    print(f"\nDice over {len(values)} classes:")
    print(f"  Mean:            {values.mean():.4f}")
    print(f"  Median:          {np.median(values):.4f}")
    print(f"  Min / Max:       {values.min():.4f} / {values.max():.4f}")
    print(f"  Classes >= 0.95: {int((values >= 0.95).sum())}/{len(values)}")
    print(f"  Classes <  0.50: {int((values <  0.50).sum())}/{len(values)}")
    _print_total(t_start)


def _print_total(t_start: float) -> None:
    elapsed = time.perf_counter() - t_start
    mm, ss = divmod(int(elapsed), 60)
    print(f"\nTotal elapsed: {mm:02d}:{ss:02d} ({elapsed:.1f}s)")


if __name__ == "__main__":
    main()
