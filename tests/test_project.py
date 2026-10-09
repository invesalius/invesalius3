import tarfile
from pathlib import Path

import numpy as np
import pytest

import invesalius.data.slice_  # noqa: F401
import invesalius.project as prj
from invesalius.utils import TwoWaysDictionary


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> prj.Project:
    """Empty project with a small image matrix stored in a file."""
    matrix = np.memmap(str(tmp_path / "image.dat"), mode="w+", dtype="int16", shape=(4, 5, 6))
    matrix[:] = np.arange(matrix.size).reshape(matrix.shape)
    matrix.flush()

    project = prj.Project()
    monkeypatch.setattr(project, "matrix_filename", matrix.filename, raising=False)
    monkeypatch.setattr(project, "matrix_shape", matrix.shape, raising=False)
    monkeypatch.setattr(project, "matrix_dtype", matrix.dtype.name, raising=False)
    monkeypatch.setattr(project, "spacing", (1.0, 1.0, 1.0), raising=False)
    monkeypatch.setattr(project, "window", 400.0, raising=False)
    monkeypatch.setattr(project, "level", 40.0, raising=False)
    monkeypatch.setattr(project, "image_versions", [("original", matrix)])
    monkeypatch.setattr(project, "mask_dict", TwoWaysDictionary())
    monkeypatch.setattr(project, "surface_dict", {})
    monkeypatch.setattr(project, "measurement_dict", {})
    return project


def test_save_keeps_matrix_shared_with_image_version(project: prj.Project, tmp_path: Path) -> None:
    project.SavePlistProject(str(tmp_path), "project.inv3")

    saved = {}
    with tarfile.open(tmp_path / "project.inv3") as tar:
        for member in tar.getmembers():
            saved[Path(member.name).name] = tar.extractfile(member).read()

    expected = project.image_versions[0][1].tobytes()
    assert saved["matrix.dat"] == expected
    assert saved["matrix_v0.dat"] == expected
