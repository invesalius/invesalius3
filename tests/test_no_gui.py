import os
import subprocess
import sys
from pathlib import Path

import nibabel as nib
import numpy as np

# These tests run in a new interpreter: with --no-gui there is no wx.App, but
# other test modules create one at import time.


def run_code(code: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", code, *args],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
    )


def test_export_surface_without_wx_app(tmp_path: Path) -> None:
    code = (
        "import sys\n"
        "import wx\n"
        "from vtkmodules.vtkFiltersSources import vtkSphereSource\n"
        "from invesalius.data.surface import Surface, SurfaceManager\n"
        "import invesalius.constants as const\n"
        "import invesalius.project as prj\n"
        "assert wx.GetApp() is None\n"
        "sphere = vtkSphereSource()\n"
        "sphere.Update()\n"
        "surface = Surface()\n"
        "surface.polydata = sphere.GetOutput()\n"
        "surface.is_shown = True\n"
        "prj.Project().surface_dict[surface.index] = surface\n"
        "SurfaceManager().OnExportSurface(sys.argv[1], const.FILETYPE_STL)\n"
    )
    path = tmp_path / "out.stl"
    result = run_code(code, str(path))
    assert result.returncode == 0, result.stderr
    assert path.exists()
    assert path.stat().st_size > 0


def run_no_gui(*cli_args: str, config_dir: Path) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["XDG_CONFIG_HOME"] = str(config_dir)
    repo_root = str(Path(__file__).resolve().parents[1])
    env["PYTHONPATH"] = repo_root + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "app.py", "--no-gui", *cli_args],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        env=env,
    )


def write_tiny_nifti(path: Path) -> None:
    data = np.zeros((8, 8, 8), dtype=np.int16)
    data[:2, :2, :2] = 100
    data[2:4, 2:4, 2:4] = 1700
    data[4:6, 4:6, 4:6] = 2500
    nib.save(nib.Nifti1Image(data, np.eye(4)), path)


def test_export_project_uses_threshold(tmp_path: Path) -> None:
    src = tmp_path / "vol.nii.gz"
    out_with = tmp_path / "with_t.nii.gz"
    out_without = tmp_path / "without_t.nii.gz"
    write_tiny_nifti(src)

    result = run_no_gui(
        "-o",
        str(src),
        "--export-project",
        str(out_with),
        "-t",
        "1000,2000",
        config_dir=tmp_path / "cfg-with",
    )
    assert result.returncode == 0, result.stderr + "\n" + result.stdout
    assert out_with.exists()

    masks = list(tmp_path.glob("with_t_mask_*"))
    assert len(masks) == 1, masks
    image = nib.load(out_with).get_fdata()
    mask = nib.load(masks[0]).get_fdata()
    selected = mask > 127
    assert selected.any()
    assert np.all((image[selected] >= 1000) & (image[selected] <= 2000))
    assert not np.any(selected & ((image < 1000) | (image > 2000)))

    result = run_no_gui(
        "-o",
        str(src),
        "--export-project",
        str(out_without),
        config_dir=tmp_path / "cfg-without",
    )
    assert result.returncode == 0, result.stderr + "\n" + result.stdout
    masks_default = list(tmp_path.glob("without_t_mask_*"))
    assert len(masks_default) == 1, masks_default
    default_mask = nib.load(masks_default[0]).get_fdata() > 127
    assert not np.array_equal(selected, default_mask)
    assert np.any(default_mask & (image > 2000))
