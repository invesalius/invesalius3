import os
import pathlib
import shutil
import sys

USER_DIR = pathlib.Path().home()
CONF_DIR = pathlib.Path(os.environ.get("XDG_CONFIG_HOME", USER_DIR.joinpath(".config")))
USER_INV_DIR = CONF_DIR.joinpath("invesalius")
USER_PRESET_DIR = USER_INV_DIR.joinpath("presets")
USER_LOG_DIR = USER_INV_DIR.joinpath("logs")
USER_RAYCASTING_PRESETS_DIRECTORY = USER_PRESET_DIR.joinpath("raycasting")

OLD_USER_INV_DIR = USER_DIR.joinpath(".invesalius")
OLD_USER_PRESET_DIR = OLD_USER_INV_DIR.joinpath("presets")
OLD_USER_LOG_DIR = OLD_USER_INV_DIR.joinpath("logs")

INV_TOP_DIR = pathlib.Path(__file__).parent.parent.resolve()

ICON_DIR = INV_TOP_DIR.joinpath("icons")
SAMPLE_DIR = INV_TOP_DIR.joinpath("samples")
DOC_DIR = INV_TOP_DIR.joinpath("docs")
RAYCASTING_PRESETS_DIRECTORY = INV_TOP_DIR.joinpath("presets", "raycasting")
RAYCASTING_PRESETS_COLOR_DIRECTORY = INV_TOP_DIR.joinpath(
    "presets", "raycasting", "color_list"
)

# Inside the windows executable
if hasattr(sys, "frozen") and (
    sys.frozen == "windows_exe" or sys.frozen == "console_exe"
):
    abs_path = INV_TOP_DIR.parent.resolve()
    ICON_DIR = abs_path.joinpath("icons")
    SAMPLE_DIR = INV_TOP_DIR.joinpath("samples")
    DOC_DIR = INV_TOP_DIR.joinpath("docs")
    RAYCASTING_PRESETS_DIRECTORY = abs_path.joinpath("presets", "raycasting")
    RAYCASTING_PRESETS_COLOR_DIRECTORY = abs_path.joinpath(
        "presets", "raycasting", "color_list"
    )
else:

    ICON_DIR = pathlib.Path(os.environ.get("INV_ICON_DIR", ICON_DIR))
    SAMPLE_DIR = pathlib.Path(os.environ.get("INV_SAMPLE_DIR", SAMPLE_DIR))
    DOC_DIR = pathlib.Path(os.environ.get("INV_DOC_DIR", DOC_DIR))
    RAYCASTING_PRESETS_DIRECTORY = pathlib.Path(
        os.environ.get("INV_RAYCASTING_PRESETS_DIR", RAYCASTING_PRESETS_DIRECTORY)
    )
    RAYCASTING_PRESETS_COLOR_DIRECTORY = pathlib.Path(
        os.environ.get("INV_RAYCASTING_COLOR_DIR", RAYCASTING_PRESETS_COLOR_DIRECTORY)
    )

# Navigation paths
CAL_DIR = INV_TOP_DIR.joinpath("navigation", "mtc_files", "CalibrationFiles")
MAR_DIR = INV_TOP_DIR.joinpath("navigation", "mtc_files", "Markers")
OBJ_DIR = INV_TOP_DIR.joinpath("navigation", "objects")

# MAC App
if not os.path.exists(ICON_DIR):
    ICON_DIR = INV_TOP_DIR.parent.parent.joinpath("icons").resolve()
    SAMPLE_DIR = INV_TOP_DIR.parent.parent.joinpath("samples").resolve()
    DOC_DIR = INV_TOP_DIR.parent.parent.joinpath("docs").resolve()


def create_conf_folders():
    USER_INV_DIR.mkdir(parents=True, exist_ok=True)
    USER_PRESET_DIR.mkdir(parents=True, exist_ok=True)
    USER_LOG_DIR.mkdir(parents=True, exist_ok=True)


def copy_old_files():
    for f in OLD_USER_INV_DIR.glob("*"):
        if f.is_file():
            print(
                shutil.copy(
                    f,
                    USER_INV_DIR.joinpath(
                        str(f).replace(str(OLD_USER_INV_DIR) + "/", "")
                    ),
                )
            )
