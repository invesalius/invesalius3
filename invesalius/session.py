# --------------------------------------------------------------------------
# Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
# Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
# Homepage:     http://www.softwarepublico.gov.br
# Contact:      invesalius@cti.gov.br
# License:      GNU - GPL 2 (LICENSE.txt/LICENCA.txt)
# --------------------------------------------------------------------------
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
# --------------------------------------------------------------------------


import codecs
import configparser as ConfigParser
import json
import os
from json.decoder import JSONDecodeError
from pathlib import Path
from random import randint
from typing import TYPE_CHECKING, Any, Dict, List, Tuple, Union

from invesalius import inv_paths
from invesalius.pubsub import pub as Publisher
from invesalius.utils import Singleton, debug, deep_merge_dict

CONFIG_PATH = os.path.join(inv_paths.USER_INV_DIR, "config.json")
OLD_CONFIG_PATH = os.path.join(inv_paths.USER_INV_DIR, "config.cfg")

STATE_PATH = os.path.join(inv_paths.USER_INV_DIR, "state.json")

SESSION_ENCODING = "utf8"

CONFIG_INIT = {
    "mode": "",
    "project_status": "",
    "debug": False,
    "debug_efield": False,
    "language": "",
    "random_id": randint(0, pow(10, 16)),
    "surface_interpolation": 1,
    "rendering": 0,
    "slice_interpolation": 0,
    "auto_reload_preview": False,
    "recent_projects": [
        (str(inv_paths.SAMPLE_DIR), "Cranium.inv3"),
    ],
    "last_dicom_folder": "",
    "file_logging": 0,
    "file_logging_level": 0,
    "append_log_file": 0,
    "logging_file": "",
    "console_logging": 0,
    "console_logging_level": 0,
    "robot": {
        "robot_ip_options": "",
    },
}


# Only one session will be initialized per time. Therefore, we use
# Singleton design pattern for implementing it
class Session(metaclass=Singleton):
    def __init__(self):
        self.temp_item = False
        self.mask_3d_preview = False
        self._config: Dict[str, Union[int, str, bool, List[Tuple[str, str]]]] = {
            "project_status": 3,
            "language": "",
            "auto_reload_preview": False,
            "file_logging": 0,
            "file_logging_level": 0,
            "append_log_file": 0,
            "logging_file": "",
            "console_logging": 0,
            "console_logging_level": 0,
        }
        self._exited_successfully_last_time = not self._ReadState()
        # If the state file was saved intentionally via "Store session", the
        # last exit was NOT a crash — override the flag so the recovery dialog
        # is never shown for a deliberate Store-session exit.
        if self._state.get("stored_session"):
            self._exited_successfully_last_time = True
        # Unsaved changes tracking
        self._has_unsaved_changes = False
        self._auto_backup_path: Union[str, None] = None
        # Backup debounce: prevent many concurrent backup threads when the
        # user is painting quickly. At most one backup every 3 seconds.
        import threading
        import time
        self._backup_lock = threading.Lock()
        self._last_backup_time = 0.0
        self.__bind_events()

    def __bind_events(self) -> None:
        Publisher.subscribe(self._Exit, "Exit session")

    def CreateConfig(self) -> None:
        import invesalius.constants as const

        self._config = CONFIG_INIT
        self._config["mode"] = const.MODE_RP
        self._config["project_status"] = const.PROJECT_STATUS_CLOSED
        self._config["robot"] = {"robot_ip_options": const.ROBOT_IPS}

        self.WriteConfigFile()

    def CheckConfig(self) -> None:
        if self._config["language"] != "":
            import invesalius.constants as const

            config_init = CONFIG_INIT
            config_init["mode"] = const.MODE_RP
            config_init["project_status"] = const.PROJECT_STATUS_CLOSED
            config_init["robot"] = {"robot_ip_options": const.ROBOT_IPS}
            self._config = deep_merge_dict(config_init, self._config.copy())
            self.WriteConfigFile()

    def CreateState(self) -> None:
        self._state: Dict[str, Any] = {}
        self.WriteStateFile()

    def DeleteStateFile(self) -> None:
        if os.path.exists(STATE_PATH):
            os.remove(STATE_PATH)
            print("Successfully deleted state file.")
        else:
            print("State file does not exist.")

    def ExitedSuccessfullyLastTime(self) -> bool:
        return self._exited_successfully_last_time

    def SetConfig(self, key: str, value: Any) -> None:
        self._config[key] = value
        self.WriteConfigFile()

    def GetConfig(self, key: str, default_value: Any = None) -> Any:
        return self._config.get(key, default_value)

    def SetState(self, key: str, value: Any) -> None:
        self._state[key] = value
        self.WriteStateFile()

    def GetState(self, key: str, default_value: Any = None) -> Any:
        return self._state.get(key, default_value)

    def IsOpen(self) -> bool:
        import invesalius.constants as const

        return self.GetConfig("project_status") != const.PROJECT_STATUS_CLOSED

    def CloseProject(self) -> None:
        import invesalius.constants as const

        debug("Session.CloseProject")
        self.SetState("project_path", None)
        self.SetConfig("project_status", const.PROJECT_STATUS_CLOSED)
        # self.mode = const.MODE_RP
        self.temp_item = False
        # Reset unsaved changes flag so a clean close is not mistaken for a crash
        self._has_unsaved_changes = False

    def SaveProject(self, path: Union[Tuple[()], Tuple[str, str]] = ()) -> None:
        import invesalius.constants as const

        debug("Session.SaveProject")
        if path:
            self.SetState("project_path", path)
            self._add_to_recent_projects(path)
        if self.temp_item:
            self.temp_item = False

        self.SetConfig("project_status", const.PROJECT_STATUS_OPENED)
        # Clear unsaved changes flag after successful save
        self._has_unsaved_changes = False
        # Remove auto-backup if it exists
        self.RemoveAutoBackup()

    def ChangeProject(self) -> None:
        import invesalius.constants as const
        import time

        debug("Session.ChangeProject")
        self.SetConfig("project_status", const.PROJECT_STATUS_CHANGED)
        # Mark project as having unsaved changes
        self._has_unsaved_changes = True

        # Debounced backup: spawn at most one backup thread every 3 seconds
        # to avoid race conditions when painting many rapid brush strokes.
        if self.IsOpen():
            now = time.time()
            if now - self._last_backup_time >= 3.0:
                self._last_backup_time = now
                from threading import Thread
                backup_thread = Thread(target=self._safe_create_backup)
                backup_thread.daemon = True
                backup_thread.start()

    def CreateProject(self, filename: str) -> None:
        import invesalius.constants as const

        debug("Session.CreateProject")
        Publisher.sendMessage("Begin busy cursor")

        # Set session info
        tempdir = str(inv_paths.TEMP_DIR)

        project_path = (tempdir, filename)
        self.SetState("project_path", project_path)

        self.temp_item = True

        self.SetConfig("project_status", const.PROJECT_STATUS_NEW)

    def OpenProject(self, filepath: "str | Path") -> None:
        import invesalius.constants as const

        debug("Session.OpenProject")

        # Add item to recent projects list (only if not an auto-backup file)
        project_path = os.path.split(filepath)
        if "temp_backup" not in str(filepath):
            self._add_to_recent_projects(project_path)

        # Set session info
        self.SetState("project_path", project_path)
        self.SetConfig("project_status", const.PROJECT_STATUS_OPENED)
        # If opened from a backup, mark as temp_item so SaveProject forces a
        # "Save As" dialog — this prevents the save from writing back into the
        # temp backup folder, which is then immediately deleted by RemoveAutoBackup.
        # Also clear the last saved directory so the Save-As dialog doesn't
        # pre-fill with the backup temp path.
        if "temp_backup" in str(filepath):
            self.temp_item = True
            self._config["last_directory_inv3"] = ""
        # Reset unsaved-changes flag: any ChangeProject() calls that fired
        # during LoadProject() (slice setup, etc.) should not count as
        # user-initiated modifications.
        self._has_unsaved_changes = False

    def WriteConfigFile(self) -> None:
        self._write_to_json(self._config, CONFIG_PATH)

    def WriteStateFile(self) -> None:
        self._write_to_json(self._state, STATE_PATH)

    def _write_to_json(self, config_dict: dict, config_filename: "str | Path") -> None:
        config_path = Path(config_filename)
        config_path.parent.mkdir(parents=True, exist_ok=True)  # Ensure parent dir exists
        with open(config_path, "w") as config_file:
            json.dump(config_dict, config_file, sort_keys=True, indent=4)

    def _add_to_recent_projects(self, item: Tuple[str, str]) -> None:
        import invesalius.constants as const

        # Recent projects list
        recent_projects: List[Tuple[str, str]] = self.GetConfig("recent_projects")
        item = list(item)

        # If item exists, remove it from list
        if recent_projects.count(item):
            recent_projects.remove(item)

        # Add new item
        recent_projects.insert(0, item)
        self.SetConfig("recent_projects", recent_projects[: const.RECENT_PROJECTS_MAXIMUM])

    def _read_config_from_json(self, json_filename: "str | Path") -> None:
        with open(json_filename) as config_file:
            config_dict = json.load(config_file)
            self._config = deep_merge_dict(self._config.copy(), config_dict)

        # Do not reading project status from the config file, since there
        # isn't a recover session tool in InVesalius yet.
        self.project_status = 3

    def _read_config_from_ini(self, config_filename: str) -> None:
        file = codecs.open(config_filename, "rb", SESSION_ENCODING)
        config = ConfigParser.ConfigParser()
        config.readfp(file)
        file.close()

        mode = config.getint("session", "mode")
        debug = config.getboolean("session", "debug")
        debug_efield = config.getboolean("session", "debug_efield")
        language = config.get("session", "language")
        last_dicom_folder = config.get("paths", "last_dicom_folder")
        # project_status = config.getint("session", "status")
        surface_interpolation = config.getint("session", "surface_interpolation")
        slice_interpolation = config.getint("session", "slice_interpolation")
        rendering = config.getint("session", "rendering")
        random_id = config.getint("session", "random_id")
        do_file_logging = config.getint("session", "do_file_logging")
        file_logging_level = config.getint("session", "file_logging_level")
        append_log_file = config.getint("session", "append_log_file")
        logging_file = config.get("session", "logging_file")
        do_console_logging = config.getint("session", "do_console_logging")
        console_logging_level = config.getint("session", "console_logging_level")

        recent_projects = eval(config.get("project", "recent_projects"))
        recent_projects = [list(rp) for rp in recent_projects]

        self.SetConfig("mode", mode)
        self.SetConfig("debug", debug)
        self.SetConfig("debug_efield", debug_efield)
        self.SetConfig("language", language)
        self.SetConfig("last_dicom_folder", last_dicom_folder)
        self.SetConfig("surface_interpolation", surface_interpolation)
        self.SetConfig("slice_interpolation", slice_interpolation)
        self.SetConfig("rendering", rendering)
        self.SetConfig("random_id", random_id)
        self.SetConfig("recent_projects", recent_projects)
        self.SetConfig("do_file_logging", do_file_logging)
        self.SetConfig("file_logging_level", file_logging_level)
        self.SetConfig("append_log_file", append_log_file)
        self.SetConfig("logging_file", logging_file)
        self.SetConfig("do_console_logging", do_console_logging)
        self.SetConfig("console_logging_level", console_logging_level)

        # Do not update project status from the config file, since there
        # isn't a recover session tool in InVesalius
        # self.SetConfig('project_status', project_status)

        #  if not(sys.platform == 'win32'):
        #  self.SetConfig('last_dicom_folder', last_dicom_folder.decode('utf-8'))

    # TODO: Make also this function private so that it is run when the class constructor is run.
    #   (Compare to _ReadState below.)
    def ReadConfig(self) -> bool:
        try:
            self._read_config_from_json(CONFIG_PATH)
        except Exception as e1:
            debug(str(e1))
            try:
                self._read_config_from_ini(OLD_CONFIG_PATH)
            except Exception as e2:
                debug(str(e2))
                return False
        # Clean up any auto-backup entries that may have been added to the
        # recent-projects list before this fix was applied.
        recent = self.GetConfig("recent_projects")
        if recent:
            cleaned = [p for p in recent if "temp_backup" not in str(p)]
            if len(cleaned) != len(recent):
                self._config["recent_projects"] = cleaned
        self.WriteConfigFile()
        return True

    def _ReadState(self) -> bool:
        success = False
        if os.path.exists(STATE_PATH):
            print("Restoring a previous state...")
            print("State file found.", STATE_PATH)

            state_file = open(STATE_PATH)
            try:
                self._state = json.load(state_file)
                success = True

            except JSONDecodeError:
                print("State file is corrupted. Deleting...")

                state_file.close()
                self.DeleteStateFile()

        if not success:
            self._state = {}

        return success

    def HasUnsavedChanges(self) -> bool:
        """Check if the project has unsaved changes."""
        return self._has_unsaved_changes

    def _safe_create_backup(self) -> None:
        """Thread-safe wrapper: acquire lock before writing the backup file
        so concurrent brush-stroke threads don't corrupt each other's writes."""
        with self._backup_lock:
            self.CreateAutoBackup()

    def CreateAutoBackup(self) -> bool:
        """
        Create (or overwrite) the auto-backup of the current project.
        Uses an atomic write pattern (write to temp file, then os.replace)
        so a crash mid-write never corrupts the last good backup.
        Returns True if backup was created successfully.
        """
        import invesalius.project as prj

        try:
            # Get current project
            project_path = self.GetState("project_path")
            if not project_path:
                return False

            # Create backup directory
            backup_dir = Path(inv_paths.USER_INV_DIR) / "temp_backup"
            backup_dir.mkdir(parents=True, exist_ok=True)

            # Write to a staging file first so that a crash mid-write never
            # corrupts the last good backup (auto_backup.inv3).
            staging_filename = "auto_backup_staging.inv3"
            staging_path = backup_dir / staging_filename
            final_filename = "auto_backup.inv3"
            final_path = backup_dir / final_filename

            # Save current project to the staging location.
            # compress=False: uncompressed tar writes ~110MB in <0.5s on NVMe.
            # Gzip compression (compress=True) was causing the multi-second UI
            # freeze — it provides no real benefit for crash-recovery backups
            # where write speed is critical. Manual saves still use their own
            # compression setting.
            proj = prj.Project()
            proj.SavePlistProject(str(backup_dir), staging_filename, compress=False)

            # Atomically promote staging → final (old backup preserved if
            # SavePlistProject raised an exception above)
            os.replace(str(staging_path), str(final_path))

            self._auto_backup_path = str(final_path)
            self.SetState("auto_backup_path", str(final_path))

            debug(f"Auto-backup updated: {final_path}")
            return True

        except Exception as e:
            debug(f"Failed to create auto-backup: {e}")
            return False

    def RemoveAutoBackup(self) -> None:
        """Remove the auto-backup file if it exists."""
        if self._auto_backup_path and os.path.exists(self._auto_backup_path):
            try:
                os.remove(self._auto_backup_path)
                debug(f"Auto-backup removed: {self._auto_backup_path}")
            except Exception as e:
                debug(f"Failed to remove auto-backup: {e}")
        
        self._auto_backup_path = None
        self.SetState("auto_backup_path", None)

    def GetAutoBackupPath(self) -> Union[str, None]:
        """Get the path to the auto-backup file if it exists."""
        backup_path = self.GetState("auto_backup_path")
        if backup_path and os.path.exists(backup_path):
            return backup_path
        return None

    def _Exit(self) -> None:
        self.CloseProject()
        # Only delete state file if no unsaved changes (for crash recovery)
        if not self._has_unsaved_changes:
            self.DeleteStateFile()
