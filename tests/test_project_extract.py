"""Regression tests for safe extraction of .inv3 projects (CVE-2024-44825)."""

import io
import os
import tarfile

import pytest

from invesalius.project import Extract


def _add_file(tar, name, data=b"data"):
    info = tarfile.TarInfo(name)
    info.size = len(data)
    tar.addfile(info, io.BytesIO(data))


def _add_symlink(tar, name, target):
    info = tarfile.TarInfo(name)
    info.type = tarfile.SYMTYPE
    info.linkname = target
    tar.addfile(info)


@pytest.fixture
def dirs(tmp_path):
    dest = tmp_path / "dest"
    outside = tmp_path / "outside"
    dest.mkdir()
    outside.mkdir()
    return tmp_path / "project.inv3", dest, outside


def test_extract_valid_project(dirs):
    archive, dest, _ = dirs
    with tarfile.open(archive, "w") as tar:
        _add_file(tar, "tmpabc/main.plist", b"plist")
        _add_file(tar, "tmpabc/matrix.dat", b"matrix")

    filelist = Extract(str(archive), str(dest))

    assert filelist == [
        os.path.join(str(dest), "tmpabc/main.plist"),
        os.path.join(str(dest), "tmpabc/matrix.dat"),
    ]
    assert (dest / "tmpabc" / "main.plist").read_bytes() == b"plist"
    assert (dest / "tmpabc" / "matrix.dat").read_bytes() == b"matrix"


def test_extract_through_symlink_is_rejected(dirs):
    """A file written through a symlink to an outside directory must not
    be extracted (the bypass of the original fix)."""
    archive, dest, outside = dirs
    with tarfile.open(archive, "w") as tar:
        _add_file(tar, "tmpabc/main.plist")
        _add_symlink(tar, "tmpabc/link", str(outside))
        _add_file(tar, "tmpabc/link/file.txt", b"pwned")

    with pytest.raises(tarfile.TarError):
        Extract(str(archive), str(dest))

    assert not (outside / "file.txt").exists()
    assert os.listdir(outside) == []


def test_symlink_pointing_outside_is_rejected(dirs):
    archive, dest, outside = dirs
    with tarfile.open(archive, "w") as tar:
        _add_file(tar, "tmpabc/main.plist")
        _add_symlink(tar, "tmpabc/link", "../../outside")

    with pytest.raises(tarfile.TarError):
        Extract(str(archive), str(dest))

    assert not (dest / "tmpabc" / "link").exists()


def test_parent_traversal_is_rejected(dirs):
    archive, dest, outside = dirs
    with tarfile.open(archive, "w") as tar:
        _add_file(tar, "tmpabc/main.plist")
        _add_file(tar, "../outside/file.txt", b"pwned")

    with pytest.raises(tarfile.TarError):
        Extract(str(archive), str(dest))

    assert os.listdir(outside) == []


def test_absolute_first_member_stays_inside_destination(dirs):
    """An absolute member name must not create directories (or files)
    outside of the destination folder."""
    archive, dest, outside = dirs
    target_dir = outside / "created_by_attacker"
    with tarfile.open(archive, "w") as tar:
        _add_file(tar, str(target_dir / "main.plist"), b"plist")

    filelist = Extract(str(archive), str(dest))

    assert not target_dir.exists()
    assert os.listdir(outside) == []
    for fname in filelist:
        assert os.path.realpath(fname).startswith(os.path.realpath(dest) + os.sep)
        assert os.path.isfile(fname)
