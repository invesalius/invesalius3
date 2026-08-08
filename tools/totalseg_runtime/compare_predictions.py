"""Compare two multilabel NIfTI segmentations with per-class Dice.

Standalone: does not import from invesalius or any GUI dependency. Both files
must have the same shape and share a class-id namespace. Canonical orientation
(RAS+) is applied to both to guard against stored-orientation differences.

Prints summary stats, the 15 worst-scoring classes with voxel counts, and any
classes present in only one of the two files.

Usage:
    python tools/totalseg_runtime/compare_predictions.py \
        --pred <pred.nii[.gz]> \
        --ref  <ref.nii[.gz]> \
        [--sidecar <task.json>]

If --sidecar points at a TotalSegmentator task JSON (with a "labels" field),
the per-class report shows anatomical names. Otherwise only class ids.
"""

import argparse
import json
from pathlib import Path

import nibabel as nib
import numpy as np


def dice_per_class(pred: np.ndarray, ref: np.ndarray):
    classes = sorted(set(np.unique(pred).tolist()) | set(np.unique(ref).tolist()))
    dices = {}
    counts = {}
    for c in classes:
        if c == 0:
            continue
        p = pred == c
        r = ref == c
        ps, rs = int(p.sum()), int(r.sum())
        counts[int(c)] = (ps, rs)
        if ps + rs == 0:
            continue
        inter = int((p & r).sum())
        dices[int(c)] = 2.0 * inter / (ps + rs)
    return dices, counts


def load_labeled(path: Path):
    img = nib.as_closest_canonical(nib.load(str(path)))
    data = img.get_fdata().astype(np.int32)
    orient = nib.orientations.aff2axcodes(img.affine)
    return data, orient


def load_id_to_name(sidecar_path):
    if sidecar_path is None or not sidecar_path.exists():
        return None
    try:
        with open(sidecar_path) as f:
            sc = json.load(f)
        return {int(idx): name for name, idx in sc.get("labels", {}).items()}
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def _fmt_row(cid, name, pv, rv, d):
    if name is not None:
        return f"{cid:>4}  {name:<32}  {pv:>10}  {rv:>10}  {d:>7.4f}"
    return f"{cid:>4}  {pv:>10}  {rv:>10}  {d:>7.4f}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pred", required=True, type=Path)
    parser.add_argument("--ref", required=True, type=Path)
    parser.add_argument(
        "--sidecar",
        type=Path,
        default=None,
        help="Optional TotalSegmentator sidecar JSON for id->name lookup.",
    )
    args = parser.parse_args()

    print(f"Loading pred: {args.pred}")
    pred, pred_orient = load_labeled(args.pred)
    print(f"  shape: {pred.shape}  orient: {pred_orient}")

    print(f"Loading ref:  {args.ref}")
    ref, ref_orient = load_labeled(args.ref)
    print(f"  shape: {ref.shape}  orient: {ref_orient}")

    if pred.shape != ref.shape:
        print(f"\nERROR: shape mismatch. pred={pred.shape} ref={ref.shape}")
        return

    id_to_name = load_id_to_name(args.sidecar)

    dices, counts = dice_per_class(pred, ref)
    values = np.array(list(dices.values()))

    print(f"\nDice over {len(values)} classes:")
    print(f"  Mean:            {values.mean():.4f}")
    print(f"  Median:          {np.median(values):.4f}")
    print(f"  Min / Max:       {values.min():.4f} / {values.max():.4f}")
    print(f"  Classes >= 0.95: {int((values >= 0.95).sum())}/{len(values)}")
    print(f"  Classes <  0.50: {int((values <  0.50).sum())}/{len(values)}")

    print("\n== Worst 15 classes ==")
    if id_to_name:
        print(f"{'id':>4}  {'name':<32}  {'pred_vox':>10}  {'ref_vox':>10}  {'dice':>7}")
    else:
        print(f"{'id':>4}  {'pred_vox':>10}  {'ref_vox':>10}  {'dice':>7}")
    for cid, d in sorted(dices.items(), key=lambda x: x[1])[:15]:
        pv, rv = counts.get(cid, (0, 0))
        name = id_to_name.get(cid, "?") if id_to_name else None
        print(_fmt_row(cid, name, pv, rv, d))

    only_in_pred = [(c, pv) for c, (pv, rv) in counts.items() if pv > 0 and rv == 0]
    only_in_ref = [(c, rv) for c, (pv, rv) in counts.items() if rv > 0 and pv == 0]

    print("\n== Present in ONE side only ==")
    print(f"Only in pred: {len(only_in_pred)} classes")
    for cid, pv in sorted(only_in_pred, key=lambda x: -x[1])[:10]:
        name = id_to_name.get(cid, "?") if id_to_name else ""
        print(f"    {cid:>4}  {name:<32}  {pv:>10} voxels")
    print(f"Only in ref:  {len(only_in_ref)} classes")
    for cid, rv in sorted(only_in_ref, key=lambda x: -x[1])[:10]:
        name = id_to_name.get(cid, "?") if id_to_name else ""
        print(f"    {cid:>4}  {name:<32}  {rv:>10} voxels")


if __name__ == "__main__":
    main()
