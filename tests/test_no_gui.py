import subprocess
import sys
from pathlib import Path

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


def test_project_load_progress_dialog_without_wx_app() -> None:
    code = (
        "import wx\n"
        "from invesalius.gui.dialogs import ProjectLoadProgressDialog\n"
        "assert wx.GetApp() is None\n"
        "dlg = ProjectLoadProgressDialog()\n"
        "assert dlg.Update(50, 'Loading project...')\n"
        "assert not dlg.WasCancelled()\n"
        "dlg.Close()\n"
    )
    result = run_code(code)
    assert result.returncode == 0, result.stderr
