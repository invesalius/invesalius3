"""Verify the migrated invesalius/.../totalseg/ produces the same Dice as the
tools/totalseg_runtime/ version. End-to-end run on a CT, compare to the
reference TotalSegmentator CLI output.

Usage:
    python tools/totalseg_runtime/verify_migration.py \
        --ct ../totalseg-test/ct.nii.gz \
        --sidecar C:/Users/jaip7/Downloads/madhan/weights/total_segmentator/ct_total_3mm.json \
        --model C:/Users/jaip7/Downloads/madhan/invesalius3/exports/total_3mm.jit \
        --reference ../totalseg-test/ref_3mm.nii.gz
"""

import argparse
import json
import time
from pathlib import Path

import numpy as np


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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ct", required=True, type=Path)
    parser.add_argument("--sidecar", required=True, type=Path)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--save-pred", type=Path, default=None)
    args = parser.parse_args()

    from invesalius.segmentation.deep_learning.totalseg.inference import load_model, run
    from invesalius.segmentation.deep_learning.totalseg.preprocess import (
        load_nifti,
        read_sidecar,
    )

    import nibabel as nib

    print(f"Loading CT:       {args.ct}")
    volume, spacing = load_nifti(str(args.ct))
    print(f"  shape (ZYX): {volume.shape}, spacing: {spacing.tolist()}")

    print(f"Loading sidecar:  {args.sidecar}")
    sidecar = read_sidecar(str(args.sidecar))

    print(f"Loading model:    {args.model}")
    handle = load_model(str(args.model), backend="jit", use_gpu=False)

    print("\nRunning inference...")
    t = time.perf_counter()
    pred = run(volume, spacing, sidecar, handle, modality="ct")
    print(f"Inference time: {time.perf_counter() - t:.2f}s")
    print(f"Pred shape (XYZ): {pred.shape}")

    if args.save_pred is not None:
        ct_img = nib.load(str(args.ct))
        out_img = nib.Nifti1Image(pred.astype(np.uint8), ct_img.affine)
        nib.save(out_img, str(args.save_pred))
        print(f"Saved prediction to: {args.save_pred}")

    print(f"\nLoading reference: {args.reference}")
    ref = nib.load(str(args.reference)).get_fdata().astype(np.int32)
    print(f"Ref shape: {ref.shape}")

    if pred.shape != ref.shape:
        print(f"ERROR: shape mismatch. pred={pred.shape} ref={ref.shape}")
        return

    dices = dice_per_class(pred, ref)
    values = np.array(list(dices.values()))

    print(f"\nDice over {len(values)} classes:")
    print(f"  Mean:           {values.mean():.4f}")
    print(f"  Median:         {np.median(values):.4f}")
    print(f"  Min / Max:      {values.min():.4f} / {values.max():.4f}")
    print(f"  Classes >= 0.95: {int((values >= 0.95).sum())}/{len(values)}")
    print(f"  Classes <  0.50: {int((values <  0.50).sum())}/{len(values)}")


if __name__ == "__main__":
    main()
