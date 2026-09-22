import pytest

from invesalius.segmentation.deep_learning.totalseg import weights as w


def test_task_registry_covers_expected_tasks():
    expected = {
        "ct_total_3mm",
        "ct_organs",
        "ct_vertebrae",
        "ct_cardiac",
        "ct_muscles",
        "ct_ribs",
        "mri_organs",
        "mri_muscles",
    }
    assert expected.issubset(set(w.TASK_REGISTRY))


def test_task_registry_entries_have_required_fields():
    for task, info in w.TASK_REGISTRY.items():
        assert "modality" in info, task
        assert "spacing_mm" in info, task
        for backend in ("jit", "onnx", "sidecar"):
            assert backend in info, f"{task} missing {backend}"
            assert "filename" in info[backend]
            assert "url" in info[backend]
            assert "hash" in info[backend]


def test_jit_and_onnx_use_lfs_media_url():
    for task, info in w.TASK_REGISTRY.items():
        for backend in ("jit", "onnx"):
            url = info[backend]["url"]
            assert url.startswith(
                "https://media.githubusercontent.com/media/"
            ), f"{task}/{backend} must use LFS media URL (got {url})"


def test_sidecar_uses_raw_url_not_media():
    # Sidecars are plain JSON in git; media URL 404s for non-LFS files.
    for task, info in w.TASK_REGISTRY.items():
        url = info["sidecar"]["url"]
        assert url.startswith(
            "https://raw.githubusercontent.com/"
        ), f"{task} sidecar must use raw URL (got {url})"


def test_weight_hashes_are_sha256_or_none():
    for task, info in w.TASK_REGISTRY.items():
        for backend in ("jit", "onnx"):
            h = info[backend]["hash"]
            assert h is not None, f"{task}/{backend} missing hash"
            assert len(h) == 64
            int(h, 16)  # raises ValueError if not hex


def test_get_model_path_unknown_task():
    with pytest.raises(ValueError):
        w.get_model_path("does_not_exist", backend="jit", cache_only=True)


def test_get_model_path_unknown_backend():
    with pytest.raises(ValueError):
        w.get_model_path("ct_organs", backend="tflite", cache_only=True)


def test_get_sidecar_path_unknown_task():
    with pytest.raises(ValueError):
        w.get_sidecar_path("does_not_exist", cache_only=True)


def test_get_model_path_cache_only_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(w.inv_paths, "MODELS_DIR", tmp_path / "sys")
    monkeypatch.setattr(w.inv_paths, "USER_DL_WEIGHTS", tmp_path / "user")
    with pytest.raises(FileNotFoundError):
        w.get_model_path("ct_organs", backend="jit", cache_only=True)


def test_get_sidecar_path_cache_only_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(w.inv_paths, "MODELS_DIR", tmp_path / "sys")
    monkeypatch.setattr(w.inv_paths, "USER_DL_WEIGHTS", tmp_path / "user")
    with pytest.raises(FileNotFoundError):
        w.get_sidecar_path("ct_organs", cache_only=True)


def test_resolve_prefers_system_over_user(tmp_path, monkeypatch):
    sys_dir = tmp_path / "sys" / "totalseg"
    user_dir = tmp_path / "user"
    sys_dir.mkdir(parents=True)
    user_dir.mkdir(parents=True)
    (sys_dir / "ct_organs.json").write_text("{}")
    (user_dir / "ct_organs.json").write_text("{}")

    monkeypatch.setattr(w.inv_paths, "MODELS_DIR", tmp_path / "sys")
    monkeypatch.setattr(w.inv_paths, "USER_DL_WEIGHTS", user_dir)

    found, path = w._resolve("ct_organs.json")
    assert found is True
    assert str(sys_dir / "ct_organs.json") == path


def test_fallback_base_url_points_at_cti_mirror():
    assert w._FALLBACK_BASE_URL.startswith("https://repo-invesalius.cti.gov.br/")
    assert "total_segmentator" in w._FALLBACK_BASE_URL


def test_download_with_fallback_uses_primary_when_it_succeeds(tmp_path, monkeypatch):
    calls = []

    def fake_download(url, dst, hash, callback, *, ssl_context=None):
        calls.append((url, ssl_context))

    monkeypatch.setattr(w, "download_url_to_file", fake_download)
    w._download_with_fallback(
        "https://primary/file.jit", "file.jit", tmp_path / "out.jit", "abc", None
    )

    assert len(calls) == 1
    assert calls[0][0] == "https://primary/file.jit"
    assert calls[0][1] is None


def test_download_with_fallback_switches_to_cti_when_primary_raises(tmp_path, monkeypatch):
    calls = []

    def fake_download(url, dst, hash, callback, *, ssl_context=None):
        calls.append((url, ssl_context))
        if len(calls) == 1:
            raise ConnectionError("primary is down")

    monkeypatch.setattr(w, "download_url_to_file", fake_download)
    w._download_with_fallback(
        "https://primary/ct_organs.jit", "ct_organs.jit", tmp_path / "out.jit", "abc", None
    )

    assert len(calls) == 2
    assert calls[0][0] == "https://primary/ct_organs.jit"
    assert calls[1][0] == f"{w._FALLBACK_BASE_URL}/ct_organs.jit"
    assert calls[1][1] is not None  # unverified SSL context passed


def test_download_with_fallback_raises_when_both_fail(tmp_path, monkeypatch):
    def fake_download(url, dst, hash, callback, *, ssl_context=None):
        raise ConnectionError(f"unreachable: {url}")

    monkeypatch.setattr(w, "download_url_to_file", fake_download)
    with pytest.raises(ConnectionError):
        w._download_with_fallback("https://primary/x", "x", tmp_path / "x", None, None)
