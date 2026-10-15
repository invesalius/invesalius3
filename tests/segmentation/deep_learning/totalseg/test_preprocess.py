import numpy as np
import pytest

from invesalius.segmentation.deep_learning.totalseg import preprocess as pp


def _fake_plans():
    return {
        "patch_size": (32, 32, 32),
        "target_spacing": [1.5, 1.5, 1.5],
        "normalization": "CTNormalization",
        "clip_low": -1000.0,
        "clip_high": 1000.0,
        "mean": 0.0,
        "std": 500.0,
    }


def test_crop_to_body_trims_zero_border():
    vol = np.zeros((10, 10, 10), dtype=np.float32)
    vol[3:7, 4:8, 5:9] = 1.0
    cropped, bbox = pp.crop_to_body(vol)
    assert cropped.shape == (4, 4, 4)
    assert bbox == [(3, 7), (4, 8), (5, 9)]
    assert np.all(cropped == 1.0)


def test_crop_to_body_all_zero_is_identity():
    vol = np.zeros((5, 5, 5), dtype=np.float32)
    cropped, bbox = pp.crop_to_body(vol)
    assert cropped.shape == vol.shape
    assert bbox == [(0, 5), (0, 5), (0, 5)]


def test_normalize_ct_clips_and_zscores():
    vol = np.array([[[-5000.0, 0.0, 5000.0]]], dtype=np.float32)
    out = pp.normalize_ct(vol, clip_low=-1000, clip_high=1000, mean=0.0, std=500.0)
    assert out.dtype == np.float32
    assert out[0, 0, 0] == pytest.approx(-2.0)
    assert out[0, 0, 1] == pytest.approx(0.0)
    assert out[0, 0, 2] == pytest.approx(2.0)


def test_normalize_mri_uses_nonzero_stats():
    vol = np.zeros((3, 3, 3), dtype=np.float32)
    vol[1, 1, 1] = 100.0
    vol[2, 2, 2] = 200.0
    out = pp.normalize_mri(vol)
    assert out.dtype == np.float32
    assert out[0, 0, 0] < 0
    assert out.mean() != pytest.approx(0.0)


def test_normalize_mri_all_zero_is_noop():
    vol = np.zeros((3, 3, 3), dtype=np.float32)
    out = pp.normalize_mri(vol)
    assert np.all(out == 0.0)


def test_resample_volume_scipy_shape():
    vol = np.random.RandomState(0).rand(20, 20, 20).astype(np.float32)
    out = pp.resample_volume(vol, np.array([2.0, 2.0, 2.0]), np.array([1.0, 1.0, 1.0]), order=3)
    assert out.shape == (40, 40, 40)
    assert out.dtype == np.float32


def test_resample_to_shape_exact():
    vol = np.random.RandomState(0).rand(10, 10, 10).astype(np.float32)
    out = pp.resample_to_shape(vol, (20, 20, 20), order=0)
    assert out.shape == (20, 20, 20)


def test_resample_to_shape_pads_or_crops_off_by_one():
    vol = np.ones((7, 7, 7), dtype=np.float32)
    out = pp.resample_to_shape(vol, (10, 10, 10), order=0)
    assert out.shape == (10, 10, 10)


def test_preprocess_populates_meta():
    vol = np.zeros((30, 30, 30), dtype=np.float32)
    vol[5:25, 5:25, 5:25] = 500.0
    spacing = np.array([2.0, 2.0, 2.0], dtype=np.float32)

    out, meta = pp.preprocess(vol, spacing, _fake_plans())

    assert out.dtype == np.float32
    assert meta["original_shape"] == vol.shape
    assert meta["bbox"] == [(5, 25), (5, 25), (5, 25)]
    assert meta["target_spacing"] == [1.5, 1.5, 1.5]


def test_preprocess_postprocess_roundtrip_shape():
    vol = np.zeros((20, 20, 20), dtype=np.float32)
    vol[3:17, 3:17, 3:17] = 300.0
    spacing = np.array([2.0, 2.0, 2.0], dtype=np.float32)

    preprocessed, meta = pp.preprocess(vol, spacing, _fake_plans())
    pred = np.zeros(preprocessed.shape, dtype=np.uint8)
    pred[0, 0, 0] = 7
    restored = pp.postprocess(pred, meta)

    assert restored.shape == vol.shape
    assert restored.dtype == np.uint8


def test_preprocess_unknown_modality():
    vol = np.ones((10, 10, 10), dtype=np.float32)
    with pytest.raises(ValueError):
        pp.preprocess(vol, np.array([1.0, 1.0, 1.0]), _fake_plans(), modality="ultrasound")
