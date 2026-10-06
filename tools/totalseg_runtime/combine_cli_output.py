"""Combine TotalSegmentator CLI per-class NIfTI output into a single multilabel
NIfTI matching the ct_total_3mm 117-class ID scheme. Useful when you already ran
TotalSegmentator (which writes one .nii.gz per class) and want to compare
against verify_migration.py which expects a single reference file.

Usage:
    python tools/totalseg_runtime/combine_cli_output.py \
        --input-dir D:/Maddy/segmentations \
        --output D:/Maddy/segmentations_ml.nii.gz \
        --task ct_total_3mm
"""

import argparse
from pathlib import Path

import nibabel as nib
import numpy as np

from invesalius.segmentation.deep_learning.totalseg.preprocess import read_sidecar
from invesalius.segmentation.deep_learning.totalseg.weights import get_sidecar_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--task", default="ct_total_3mm")
    args = parser.parse_args()

    sidecar = read_sidecar(str(get_sidecar_path(args.task)))
    # sidecar["labels"] is {"name": id}; invert to {name: id} with int values.
    name_to_id = {name: int(idx) for name, idx in sidecar["labels"].items() if int(idx) != 0}
    print(f"Task '{args.task}' has {len(name_to_id)} non-background classes.")

    combined = None
    affine = None
    matched = 0
    missing = []

    for name, class_id in name_to_id.items():
        f = args.input_dir / f"{name}.nii.gz"
        if not f.exists():
            f = args.input_dir / f"{name}.nii"
        if not f.exists():
            missing.append(name)
            continue

        img = nib.load(str(f))
        data = img.get_fdata().astype(np.uint8)
        if combined is None:
            combined = np.zeros(data.shape, dtype=np.uint8)
            affine = img.affine
        combined[data > 0] = class_id
        matched += 1

    if combined is None:
        raise RuntimeError(f"No matching .nii/.nii.gz files found in {args.input_dir}")

    print(f"Matched {matched} / {len(name_to_id)} classes.")
    if missing:
        print(f"Missing (first 10): {missing[:10]}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    nib.save(nib.Nifti1Image(combined, affine), str(args.output))
    print(
        f"Wrote {args.output}  shape={combined.shape}  unique={sorted(np.unique(combined).tolist())[:20]}"
    )


if __name__ == "__main__":
    main()
