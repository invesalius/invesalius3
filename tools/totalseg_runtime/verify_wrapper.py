"""Verify that the TotalSegProcess wrapper's inference path produces the same
label map as verify_migration.py (which validated Dice 0.9994 vs. the CLI).

This does not import TotalSegProcess directly (that pulls in wx/vtk via the
Slice module chain, which isn't available headless). Instead it duplicates the
wrapper's _run_segmentation flow using the same underlying modules, feeding
the volume in InVesalius layout (ZYX matrix + XYZ spacing) and using the new
output_layout="zyx" path. If this matches verify_migration.py's output, the
wrapper is behavior-preserving.

Model + sidecar are resolved via the same auto-downloader the runtime uses
(weights.get_model_path / weights.get_sidecar_path). If a file is missing
locally it will be fetched to USER_DL_WEIGHTS with SHA256 verification.

Usage:
    python tools/totalseg_runtime/verify_wrapper.py \
        --ct ../totalseg-test/ct.nii.gz \
        --task ct_total_3mm \
        --backend jit \
        --reference ../totalseg-test/ref_3mm.nii.gz
"""

import argparse
import time
from pathlib import Path

import nibabel as nib
import numpy as np

from invesalius.segmentation.deep_learning.totalseg.inference import load_model, run
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ct", required=True, type=Path)
    parser.add_argument("--task", default="ct_total_3mm", help="Task name from TASK_REGISTRY")
    parser.add_argument("--backend", default="jit", choices=("jit", "onnx"))
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--save-pred", type=Path, default=None)
    args = parser.parse_args()

    print(f"Task:             {args.task}")
    print(f"Backend:          {args.backend}")

    # Resolve (and download if missing) via the same path the wrapper uses.
    print("Resolving sidecar...")
    sidecar_path = get_sidecar_path(args.task, progress_callback=_download_progress("sidecar"))
    print(f"\n  sidecar: {sidecar_path}")

    print("Resolving model weights...")
    model_path = get_model_path(
        args.task, args.backend, progress_callback=_download_progress("weights")
    )
    print(f"\n  model:   {model_path}")

    print(f"\nLoading CT:       {args.ct}")
    volume_zyx, spacing_zyx = load_nifti(str(args.ct))
    invesalius_matrix = volume_zyx  # InVesalius matrix layout
    invesalius_spacing_xyz = tuple(float(s) for s in spacing_zyx[::-1])  # XYZ order
    print(f"  matrix shape (ZYX): {invesalius_matrix.shape}")
    print(f"  spacing (XYZ from InVesalius convention): {invesalius_spacing_xyz}")

    sidecar = read_sidecar(str(sidecar_path))
    handle = load_model(str(model_path), backend=args.backend, use_gpu=False)

    # Duplicate what TotalSegProcess._run_segmentation does
    volume_ready = np.ascontiguousarray(invesalius_matrix, dtype=np.float32)
    spacing_ready = np.array(invesalius_spacing_xyz[::-1], dtype=np.float32)
    print(f"  volume passed to run() shape: {volume_ready.shape}")
    print(f"  spacing passed to run() (should be ZYX): {spacing_ready.tolist()}")

    print("\nRunning inference (output_layout='zyx' path)...")
    t = time.perf_counter()
    pred_zyx = run(
        volume_ready,
        spacing_ready,
        sidecar,
        handle,
        modality=sidecar.get("modality", "CT").lower(),
        output_layout="zyx",
    )
    print(f"Inference time: {time.perf_counter() - t:.2f}s")
    print(f"Wrapper-path prediction shape (ZYX): {pred_zyx.shape}")

    # Reference: verify_migration produces XYZ output (default output_layout="input").
    # Load and transpose to ZYX for comparison.
    print(f"\nLoading reference: {args.reference}")
    ref_nib = nib.load(str(args.reference)).get_fdata().astype(np.int32)
    ref_zyx = ref_nib.transpose(2, 1, 0)
    print(f"Ref shape (transposed to ZYX): {ref_zyx.shape}")

    if pred_zyx.shape != ref_zyx.shape:
        print(f"ERROR: shape mismatch. pred={pred_zyx.shape} ref={ref_zyx.shape}")
        return

    dices = dice_per_class(pred_zyx, ref_zyx)
    values = np.array(list(dices.values()))
    print(f"\nDice over {len(values)} classes:")
    print(f"  Mean:            {values.mean():.4f}")
    print(f"  Median:          {np.median(values):.4f}")
    print(f"  Min / Max:       {values.min():.4f} / {values.max():.4f}")
    print(f"  Classes >= 0.95: {int((values >= 0.95).sum())}/{len(values)}")
    print(f"  Classes <  0.50: {int((values <  0.50).sum())}/{len(values)}")

    if args.save_pred is not None:
        # Save transposed back to XYZ so ITK-SNAP loads it correctly against the CT.
        pred_xyz = pred_zyx.transpose(2, 1, 0)
        ct_img = nib.load(str(args.ct))
        out_img = nib.Nifti1Image(pred_xyz.astype(np.uint8), ct_img.affine)
        nib.save(out_img, str(args.save_pred))
        print(f"Saved prediction to: {args.save_pred}")

    print("\nExpected: same Dice as verify_migration.py (~0.9994 mean, all >= 0.95).")
    print("If it matches, the wrapper's layout handling + output_layout='zyx' path is correct.")


if __name__ == "__main__":
    main()
