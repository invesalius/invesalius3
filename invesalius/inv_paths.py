# --------------------------------------------------------------------
# Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
# Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
# Homepage:     http://www.softwarepublico.gov.br
# Contact:      invesalius@cti.gov.br
# License:      GNU - GPL 2 (LICENSE.txt/LICENCA.txt)
# --------------------------------------------------------------------
#    Este programa e software livre; voce pode redistribui-lo e/ou
#    modifica-lo sob os termos da Licenca Publica Geral GNU, conforme
#    publicada pela Free Software Foundation; de acordo com a versao 2
#    da Licenca.
#
#    Este programa eh distribuido na expectativa de ser util, mas SEM
#    QUALQUER GARANTIA; sem mesmo a garantia implicita de
#    COMERCIALIZACAO ou de ADEQUACAO A QUALQUER PROPOSITO EM
#    PARTICULAR. Consulte a Licenca Publica Geral GNU para obter mais
#    detalhes.
# --------------------------------------------------------------------
import os
import pathlib
import shutil
import sys
import tempfile

HOME_DIR = pathlib.Path().home()
CONF_DIR = pathlib.Path(os.environ.get("XDG_CONFIG_HOME", HOME_DIR.joinpath(".config")))
USER_INV_DIR = CONF_DIR.joinpath("invesalius")
USER_PRESET_DIR = USER_INV_DIR.joinpath("presets")
USER_LOG_DIR = USER_INV_DIR.joinpath("logs")
USER_DL_WEIGHTS = USER_INV_DIR.joinpath("deep_learning/weights/")
USER_RAYCASTING_PRESETS_DIRECTORY = USER_PRESET_DIR.joinpath("raycasting")
TEMP_DIR = tempfile.gettempdir()

USER_PLUGINS_DIRECTORY = USER_INV_DIR.joinpath("plugins")

OLD_USER_INV_DIR = HOME_DIR.joinpath(".invesalius")
OLD_USER_PRESET_DIR = OLD_USER_INV_DIR.joinpath("presets")
OLD_USER_LOG_DIR = OLD_USER_INV_DIR.joinpath("logs")

INV_TOP_DIR = pathlib.Path(__file__).parent.parent.resolve()

PLUGIN_DIRECTORY = INV_TOP_DIR.joinpath("plugins")

ICON_DIR = INV_TOP_DIR.joinpath("icons")
SAMPLE_DIR = INV_TOP_DIR.joinpath("samples")
DOC_DIR = INV_TOP_DIR.joinpath("docs")
RAYCASTING_PRESETS_DIRECTORY = INV_TOP_DIR.joinpath("presets", "raycasting")
RAYCASTING_PRESETS_COLOR_DIRECTORY = INV_TOP_DIR.joinpath("presets", "raycasting", "color_list")

MODELS_DIR = INV_TOP_DIR.joinpath("ai")
LOCALE_DIR = INV_TOP_DIR.joinpath("locale")

# Inside the windows executable
if hasattr(sys, "frozen") and (
    getattr(sys, "frozen") == "windows_exe" or getattr(sys, "frozen") == "console_exe"
):
    abs_path = INV_TOP_DIR.parent.resolve()
    ICON_DIR = abs_path.joinpath("icons")
    SAMPLE_DIR = INV_TOP_DIR.joinpath("samples")
    DOC_DIR = INV_TOP_DIR.joinpath("docs")
    RAYCASTING_PRESETS_DIRECTORY = abs_path.joinpath("presets", "raycasting")
    RAYCASTING_PRESETS_COLOR_DIRECTORY = abs_path.joinpath("presets", "raycasting", "color_list")
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
OBJ_DIR = str(INV_TOP_DIR.joinpath("navigation", "objects"))

MTC_CAL_DIR = str(INV_TOP_DIR.joinpath("navigation", "mtc_files", "CalibrationFiles"))
MTC_MAR_DIR = str(INV_TOP_DIR.joinpath("navigation", "mtc_files", "Markers"))

NDI_MAR_DIR_PROBE = str(INV_TOP_DIR.joinpath("navigation", "ndi_files", "Markers", "8700340.rom"))
NDI_MAR_DIR_REF = str(INV_TOP_DIR.joinpath("navigation", "ndi_files", "Markers", "8700339.rom"))
NDI_MAR_DIR_OBJ = str(INV_TOP_DIR.joinpath("navigation", "ndi_files", "Markers", "8700338.rom"))

OPTITRACK_CAL_DIR = str(INV_TOP_DIR.joinpath("navigation", "optitrack_files", "Calibration.cal"))
OPTITRACK_USERPROFILE_DIR = str(
    INV_TOP_DIR.joinpath("navigation", "optitrack_files", "UserProfile.motive")
)
# MAC App
if not os.path.exists(ICON_DIR):
    ICON_DIR = INV_TOP_DIR.parent.parent.joinpath("icons").resolve()
    SAMPLE_DIR = INV_TOP_DIR.parent.parent.joinpath("samples").resolve()
    DOC_DIR = INV_TOP_DIR.parent.parent.joinpath("docs").resolve()


def create_conf_folders() -> None:
    USER_INV_DIR.mkdir(parents=True, exist_ok=True)
    USER_PRESET_DIR.mkdir(parents=True, exist_ok=True)
    USER_LOG_DIR.mkdir(parents=True, exist_ok=True)
    USER_DL_WEIGHTS.mkdir(parents=True, exist_ok=True)
    USER_PLUGINS_DIRECTORY.mkdir(parents=True, exist_ok=True)


def copy_old_files() -> None:
    for f in OLD_USER_INV_DIR.glob("*"):
        if f.is_file():
            print(
                shutil.copy(
                    f,
                    USER_INV_DIR.joinpath(str(f).replace(str(OLD_USER_INV_DIR) + "/", "")),
                )
            )
