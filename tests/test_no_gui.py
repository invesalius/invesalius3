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
        "SurfaceManager()._export_surface(sys.argv[1], const.FILETYPE_STL, convert_to_world=False)\n"
    )
    path = tmp_path / "out.stl"
    result = run_code(code, str(path))
    assert result.returncode == 0, result.stderr
    assert path.exists()
    assert path.stat().st_size > 0


def test_save_project_without_wx_app(tmp_path: Path) -> None:
    code = (
        "import sys\n"
        "import wx\n"
        "import invesalius.i18n as i18n\n"
        "i18n.InstallLanguage('en')\n"
        "from invesalius.control import Controller\n"
        "import invesalius.project as prj\n"
        "import invesalius.session as ses\n"
        "def save_plist_project(self, *args, **kwargs):\n"
        "    pass\n"
        "def save_session_project(self, *args, **kwargs):\n"
        "    pass\n"
        "prj.Project.SavePlistProject = save_plist_project\n"
        "ses.Session.SaveProject = save_session_project\n"
        "assert wx.GetApp() is None\n"
        "Controller(None).SaveProject(sys.argv[1])\n"
    )
    result = run_code(code, str(tmp_path / "out.inv3"))
    assert result.returncode == 0, result.stderr
