"""Verify the migrated invesalius/.../totalseg/ produces the same Dice as the
tools/totalseg_runtime/ version. End-to-end run on a CT, compare to the
reference TotalSegmentator CLI output.

Two modes via --layout:
  --layout xyz (default): tests the standalone path used by nibabel callers.
    Volume comes in as XYZ, run() transposes to ZYX internally, returns XYZ.
  --layout zyx: tests the wrapper path used by TotalSegProcess inside
    InVesalius. Volume is passed in ZYX (matching Slice matrix), spacing is
    reversed to ZYX, run() skips the final transpose via output_layout="zyx".

Both modes should produce the same Dice against the reference.

Usage:
    python tools/totalseg_runtime/verify_migration.py \
        --ct ../totalseg-test/ct.nii.gz \
        --task ct_total_3mm \
        --backend jit \
        --reference ../totalseg-test/ref_3mm.nii.gz \
        --layout xyz
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
    parser.add_argument(
        "--layout",
        default="xyz",
        choices=("xyz", "zyx"),
        help="xyz: standalone path (default). zyx: wrapper path used by TotalSegProcess.",
    )
    parser.add_argument("--save-pred", type=Path, default=None)
    args = parser.parse_args()

    print(f"Task:             {args.task}")
    print(f"Backend:          {args.backend}")
    print(f"Layout:           {args.layout}")

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
    print(f"  shape (ZYX): {volume_zyx.shape}, spacing: {spacing_zyx.tolist()}")

    sidecar = read_sidecar(str(sidecar_path))
    handle = load_model(str(model_path), backend=args.backend, use_gpu=False)

    # spacing_zyx from load_nifti is already ZYX. In "zyx" mode we pass it
    # straight through and skip the final transpose so we get ZYX output too.
    output_layout = "zyx" if args.layout == "zyx" else "input"
    pred = _run_with_layout(volume_zyx, spacing_zyx, sidecar, handle, output_layout=output_layout)
    ref_expected_layout = "zyx" if args.layout == "zyx" else "xyz"

    print(f"Pred shape: {pred.shape}")

    if args.save_pred is not None:
        # Always save NIfTI in XYZ so ITK-SNAP loads correctly against the CT.
        pred_xyz = pred.transpose(2, 1, 0) if args.layout == "zyx" else pred
        ct_img = nib.load(str(args.ct))
        out_img = nib.Nifti1Image(pred_xyz.astype(np.uint8), ct_img.affine)
        nib.save(out_img, str(args.save_pred))
        print(f"Saved prediction to: {args.save_pred}")

    print(f"\nLoading reference: {args.reference}")
    ref = nib.load(str(args.reference)).get_fdata().astype(np.int32)
    if ref_expected_layout == "zyx":
        ref = ref.transpose(2, 1, 0)
    print(f"Ref shape: {ref.shape}")

    if pred.shape != ref.shape:
        print(f"ERROR: shape mismatch. pred={pred.shape} ref={ref.shape}")
        return

    dices = dice_per_class(pred, ref)
    values = np.array(list(dices.values()))

    print(f"\nDice over {len(values)} classes:")
    print(f"  Mean:            {values.mean():.4f}")
    print(f"  Median:          {np.median(values):.4f}")
    print(f"  Min / Max:       {values.min():.4f} / {values.max():.4f}")
    print(f"  Classes >= 0.95: {int((values >= 0.95).sum())}/{len(values)}")
    print(f"  Classes <  0.50: {int((values <  0.50).sum())}/{len(values)}")


def _run_with_layout(volume, spacing, sidecar, handle, output_layout):
    print(f"\nRunning inference (output_layout='{output_layout}')...")
    t = time.perf_counter()
    pred = run(
        volume,
        spacing,
        sidecar,
        handle,
        modality=sidecar.get("modality", "CT").lower(),
        output_layout=output_layout,
    )
    print(f"Inference time: {time.perf_counter() - t:.2f}s")
    return pred


if __name__ == "__main__":
    main()
