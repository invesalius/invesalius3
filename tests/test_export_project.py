import argparse
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import nibabel as nib
import numpy as np
import pytest

# slice_ has to be imported before project, otherwise they fail on a circular import.
from invesalius.data.slice_ import Slice  # noqa: F401
from invesalius.project import Project
from invesalius.session import Session

# Importing app reads and rewrites the user's config file, and the values it loads
# leak into the Session singleton used by other tests.
with patch.object(Session, "ReadConfig", return_value=False):
    from app import add_suffix, check_for_export


def make_args(export_project: str) -> argparse.Namespace:
    return argparse.Namespace(
        export=None, export_to_all=None, export_project=export_project, save_masks=False
    )


@pytest.fixture
def fake_slice():
    fake = SimpleNamespace(matrix=np.ones((2, 3, 4), dtype=np.int16), spacing=(1.0, 1.0, 2.0))
    with patch("invesalius.data.slice_.Slice", return_value=fake):
        yield fake


@pytest.mark.parametrize(
    "filename, expected",
    [
        ("out.nii.gz", "out-SERIES.nii.gz"),
        ("out.NII.GZ", "out-SERIES.NII.GZ"),
        ("out.nii", "out-SERIES.nii"),
        ("out.hdf5", "out-SERIES.hdf5"),
        ("out.h5", "out-SERIES.h5"),
        ("out", "out-SERIES"),
        ("some.dir/out.nii.gz", "some.dir/out-SERIES.nii.gz"),
        ("some.dir/out", "some.dir/out-SERIES"),
    ],
)
def test_add_suffix(filename: str, expected: str) -> None:
    assert add_suffix(filename, "SERIES") == expected


@pytest.mark.parametrize(
    "filename, writer",
    [
        ("out.hdf5", "export_project_to_hdf5"),
        ("out.h5", "export_project_to_hdf5"),
        ("OUT.HDF5", "export_project_to_hdf5"),
        ("out.nii", "export_project_to_nifti"),
        ("out.nii.gz", "export_project_to_nifti"),
        ("OUT.NII.GZ", "export_project_to_nifti"),
    ],
)
def test_export_project_selects_writer(filename: str, writer: str) -> None:
    with patch.object(Project, writer) as mock_writer:
        Project().export_project(filename, save_masks=False)
    mock_writer.assert_called_once_with(filename, False)


@pytest.mark.parametrize("filename", ["out", "out.xyz", "out.nii-SERIES.gz"])
def test_export_project_rejects_unknown_extension(filename: str) -> None:
    with pytest.raises(ValueError, match="Unsupported export format"):
        Project().export_project(filename, save_masks=False)


def test_check_for_export_writes_nii_gz_with_suffix(
    fake_slice, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    expected = tmp_path / "out-SERIES.nii.gz"

    check_for_export(make_args(str(tmp_path / "out.nii.gz")), suffix="SERIES")

    assert nib.load(expected).shape == (4, 3, 2)
    assert f"Saved {expected}" in capsys.readouterr().out


@pytest.mark.parametrize("suffix", ["", "SERIES"])
def test_check_for_export_fails_on_unknown_extension(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], suffix: str
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        check_for_export(make_args(str(tmp_path / "out.xyz")), suffix=suffix)

    assert exc_info.value.code == 1
    output = capsys.readouterr().out
    assert "Unsupported export format" in output
    assert "Saved" not in output
    assert list(tmp_path.iterdir()) == []
