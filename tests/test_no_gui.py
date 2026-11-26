import os
import subprocess
import sys
from pathlib import Path

# These tests run in a new interpreter: with --no-gui there is no wx.App, but
# other test modules create one at import time.


def run_code(
    code: str, *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", code, *args],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        env=env,
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


def test_save_project_without_wx_app(tmp_path: Path) -> None:
    code = (
        "import sys\n"
        "import numpy as np\n"
        "import nibabel as nib\n"
        "import wx\n"
        "import invesalius.session as ses\n"
        "from invesalius.control import Controller\n"
        "from invesalius.pubsub import pub as Publisher\n"
        "assert wx.GetApp() is None\n"
        "data = np.random.default_rng(0).integers(0, 1000, (8, 8, 8)).astype(np.int16)\n"
        "nib.save(nib.Nifti1Image(data, np.eye(4)), sys.argv[1])\n"
        "session = ses.Session()\n"
        "if not session.ReadConfig():\n"
        "    session.CreateConfig()\n"
        "controller = Controller(None)\n"
        "Publisher.sendMessage('Open other files', filepath=sys.argv[1])\n"
        "Publisher.sendMessage('Save project', filepath=sys.argv[2])\n"
    )
    volume = tmp_path / "volume.nii"
    path = tmp_path / "out.inv3"
    env = {**os.environ, "XDG_CONFIG_HOME": str(tmp_path / "config"), "HOME": str(tmp_path)}
    result = run_code(code, str(volume), str(path), env=env)
    assert result.returncode == 0, result.stderr
    assert path.exists()
    assert path.stat().st_size > 0
