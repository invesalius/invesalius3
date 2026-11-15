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
import tarfile
import tempfile
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from json.decoder import JSONDecodeError
from pathlib import Path
from random import randint
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    List,
    NamedTuple,
    Optional,
    Sequence,
    Set,
    Tuple,
    Union,
)

from invesalius import inv_paths
from invesalius.pubsub import pub as Publisher
from invesalius.utils import Singleton, debug, deep_merge_dict

# Minimum time, in seconds, between the start of two auto-backups.
AUTO_BACKUP_MIN_INTERVAL = 3.0
# The auto-backup only starts after the project has gone this many seconds
# without changes, so it does not run while the user drags the threshold
# slider or paints with the brush.
AUTO_BACKUP_IDLE_DELAY = 5.0
# During uninterrupted editing, a backup is still made at least this often.
AUTO_BACKUP_MAX_DELAY = 15.0

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
    "server_aetitle": "INVESALIUS",
    "server_port": 11120,
    'nodes': [],
    'selected_node': {},
    'store_path': str(inv_paths.USER_DICOM_DIR),
    'server_ip': "",
    'download_method': "CMOVE"
}


def write_backup_archive(
    folder_name: str,
    files: Sequence[Tuple[str, str]],
    staging_path: str,
    final_path: str,
) -> str:
    """
    Write ``files`` into an uncompressed .inv3 archive and publish it atomically.

    Same layout as project.Compress(compress=False): every file goes under
    ``folder_name`` inside the archive. The archive is written to
    ``staging_path`` and only then moved to ``final_path`` with os.replace, so a
    crash mid-write never corrupts the last good backup.

    Runs in the auto-backup thread (or on the caller's thread for
    Session.CreateAutoBackup), so it must not touch wx, VTK or Session state.

    Args:
        folder_name: Name of the top-level folder inside the archive.
        files: ``(source_path, name_inside_archive)`` pairs.
        staging_path: Temporary file the archive is written to.
        final_path: Path of the finished backup.

    Returns:
        ``final_path``.
    """
    try:
        with tarfile.open(staging_path, "w") as tar:
            for source, arcname in files:
                arcname = os.path.normpath(arcname)  # Sanitizing path
                if ".." in arcname or os.path.isabs(arcname):
                    continue

                if not os.path.exists(source):
                    if arcname.startswith("matrix"):
                        raise FileNotFoundError(
                            f"Critical project file missing during backup: {source} "
                            f"(target: {arcname})."
                        )
                    # A mask or surface removed while the backup was being prepared.
                    continue

                tar.add(source, arcname=os.path.join(folder_name, arcname))
        os.replace(staging_path, final_path)
    except BaseException:
        try:
            os.remove(staging_path)
        except OSError:
            pass
        raise
    return final_path


class _BackupJob(NamedTuple):
    """An auto-backup ready to be written by write_backup_archive."""

    folder_name: str
    files: List[Tuple[str, str]]
    staging_path: str
    final_path: str
    # Temporary files from Project.CollectSaveFiles, removed after writing.
    dir_temp: str
    temp_files: Set[str]


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
        # Auto-backup: the archive is written in the background, by a worker
        # thread. At most one backup runs at a time, and backups start at least
        # AUTO_BACKUP_MIN_INTERVAL seconds apart. The attributes below are only
        # touched from the main thread (except in the no-GUI fallback).
        self._backup_lock = threading.Lock()
        self._last_backup_time = 0.0
        self._backup_executor: Optional[ThreadPoolExecutor] = None
        # (future, job, generation) of the backup being written, if any.
        self._backup_inflight: Optional[Tuple[Future, _BackupJob, int]] = None
        self._backup_timer: Any = None  # wx.CallLater of the next backup
        # time.monotonic() of the first change not yet included in a backup.
        self._backup_requested_time: Optional[float] = None
        self._backup_pending = False  # project changed while a backup was running
        # Incremented when the backup is removed (e.g. project saved), so a
        # backup that was still being written is discarded when it finishes.
        self._backup_generation = 0
        self.__bind_events()

    def __bind_events(self) -> None:
        Publisher.subscribe(self._Exit, "Exit session")

    def CreateConfig(self) -> None:
        import invesalius.constants as const

        self._config = CONFIG_INIT
        self._config["mode"] = const.MODE_RP
        self._config["project_status"] = const.PROJECT_STATUS_CLOSED

        self.WriteConfigFile()

    def CheckConfig(self) -> None:
        if self._config["language"] != "":
            import invesalius.constants as const

            config_init = CONFIG_INIT
            config_init["mode"] = const.MODE_RP
            config_init["project_status"] = const.PROJECT_STATUS_CLOSED
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

        debug("Session.ChangeProject")
        self.SetConfig("project_status", const.PROJECT_STATUS_CHANGED)
        # Mark project as having unsaved changes
        self._has_unsaved_changes = True

        if self.IsOpen():
            self._schedule_backup()

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

        server_aetitle = config.get('session','server_aetitle')
        server_port = config.get('session','server_port')
        nodes = config.get('session','nodes')
        selected_node = config.get('session','selected_node')
        store_path = config.get('session','store_path')
        server_ip = config.get('session','server_ip')
        download_method = config.get('session', 'download_method')

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
        self.SetConfig('server_aetitle', server_aetitle)
        self.SetConfig('server_port', server_port)
        self.SetConfig('nodes', nodes)
        self.SetConfig('selected_node', selected_node)
        self.SetConfig('store_path', store_path)
        self.SetConfig('server_ip', server_ip)
        self.SetConfig('download_method', download_method)

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
        so concurrent callers don't corrupt each other's writes."""
        with self._backup_lock:
            self.CreateAutoBackup()

    def _schedule_backup(self) -> None:
        """
        Request an auto-backup of the current project, written in the background.

        Requests are coalesced: the backup starts only after
        AUTO_BACKUP_IDLE_DELAY seconds without changes (but no later than
        AUTO_BACKUP_MAX_DELAY seconds after the first pending change), at most one
        backup runs at a time, and backups start at least AUTO_BACKUP_MIN_INTERVAL
        seconds apart. A change made while a backup is running triggers one more
        backup when it finishes, so the latest change is always included in the end.
        """
        import wx

        if wx.GetApp() is None:
            # No GUI event loop (e.g. scripted use): back up from a thread.
            now = time.monotonic()
            if now - self._last_backup_time >= AUTO_BACKUP_MIN_INTERVAL:
                self._last_backup_time = now
                threading.Thread(target=self._safe_create_backup, daemon=True).start()
            return

        if not wx.IsMainThread():
            wx.CallAfter(self._schedule_backup)
            return

        now = time.monotonic()
        if self._backup_inflight is not None:
            self._backup_pending = True
            if self._backup_requested_time is None:
                self._backup_requested_time = now
            return

        if self._backup_requested_time is None:
            self._backup_requested_time = now
        # Wait until the user stops editing, but not beyond the maximum delay,
        # and keep the minimum interval since the previous backup.
        wait = min(
            AUTO_BACKUP_IDLE_DELAY,
            AUTO_BACKUP_MAX_DELAY - (now - self._backup_requested_time),
        )
        wait = max(wait, AUTO_BACKUP_MIN_INTERVAL - (now - self._last_backup_time), 0.0)
        millis = int(wait * 1000) + 1

        if self._backup_timer is not None:
            # Postpone the scheduled backup: the project is still being edited.
            self._backup_timer.Restart(millis)
        else:
            self._backup_timer = wx.CallLater(millis, self._start_async_backup)

    def _start_async_backup(self) -> None:
        """Prepare the backup on the main thread and hand the writing to the worker."""
        self._backup_timer = None
        self._backup_pending = False
        self._backup_requested_time = None
        if self._backup_inflight is not None or not self.IsOpen():
            return

        self._last_backup_time = time.monotonic()
        job = self._prepare_backup_job()
        if job is None:
            return

        try:
            future = self._get_backup_executor().submit(
                write_backup_archive, job.folder_name, job.files, job.staging_path, job.final_path
            )
        except Exception as e:
            debug(f"Failed to start auto-backup: {e}")
            self._cleanup_backup_job(job)
            return

        generation = self._backup_generation
        self._backup_inflight = (future, job, generation)
        future.add_done_callback(lambda f: self._on_backup_future_done(f, job, generation))

    def _on_backup_future_done(self, future: Future, job: _BackupJob, generation: int) -> None:
        """Called from an executor thread: finish the backup on the main thread."""
        import wx

        try:
            wx.CallAfter(self._finish_async_backup, future, job, generation)
        except Exception:
            # The wx application is gone (exiting): just remove the temp files.
            self._cleanup_backup_job(job)

    def _finish_async_backup(self, future: Future, job: _BackupJob, generation: int) -> None:
        if self._backup_inflight is None or self._backup_inflight[0] is not future:
            return  # already finished by CreateAutoBackup or _ShutdownBackup
        self._backup_inflight = None
        self._cleanup_backup_job(job)

        try:
            final_path = future.result()
        except Exception as e:
            debug(f"Failed to create auto-backup: {e}")
        else:
            if generation == self._backup_generation:
                self._auto_backup_path = final_path
                self.SetState("auto_backup_path", final_path)
                debug(f"Auto-backup updated: {final_path}")
            else:
                # The backup was removed (e.g. project saved) while this one
                # was being written, so it is already out of date.
                self._remove_file(final_path)

        if self._backup_pending:
            self._backup_pending = False
            if self.IsOpen():
                self._schedule_backup()

    def _wait_backup_inflight(self) -> None:
        """Block until the backup being written (if any) finishes, and finish it."""
        inflight = self._backup_inflight
        if inflight is None:
            return
        try:
            inflight[0].result()
        except Exception:
            pass  # reported by _finish_async_backup
        self._finish_async_backup(*inflight)

    def _get_backup_executor(self) -> ThreadPoolExecutor:
        if self._backup_executor is None:
            # A single thread, kept alive and reused by every backup.
            self._backup_executor = ThreadPoolExecutor(
                max_workers=1, thread_name_prefix="auto_backup"
            )
        return self._backup_executor

    def _shutdown_backup_executor(self, wait: bool) -> None:
        executor = self._backup_executor
        self._backup_executor = None
        if executor is not None:
            try:
                executor.shutdown(wait=wait, cancel_futures=True)
            except Exception as e:
                debug(f"Failed to stop the auto-backup worker: {e}")

    def _prepare_backup_job(self) -> Optional[_BackupJob]:
        """
        Collect the files of the current project for a backup.

        Cheap part of the backup (plists and file list); must run on the main
        thread. Returns None if there is nothing to back up or it failed.
        """
        import invesalius.project as prj

        if not self.GetState("project_path"):
            return None

        staging_path = None
        try:
            backup_dir = Path(inv_paths.USER_INV_DIR) / "temp_backup"
            backup_dir.mkdir(parents=True, exist_ok=True)

            # A unique staging file per backup, so two backups never write to
            # the same file. It is moved to auto_backup.inv3 once complete.
            fd, staging_path = tempfile.mkstemp(
                prefix="auto_backup_staging_", suffix=".inv3", dir=str(backup_dir)
            )
            os.close(fd)

            # compress=False: gzip would make the backup much slower and gives
            # no real benefit for crash recovery. Manual saves still use their
            # own compression setting.
            dir_temp, filelist, temp_files = prj.Project().CollectSaveFiles(compress=False)
        except Exception as e:
            debug(f"Failed to prepare auto-backup: {e}")
            if staging_path is not None:
                self._remove_file(staging_path)
            return None

        return _BackupJob(
            folder_name=os.path.basename(dir_temp),
            files=[(str(src), str(arcname)) for src, arcname in filelist.items()],
            staging_path=staging_path,
            final_path=str(backup_dir / "auto_backup.inv3"),
            dir_temp=dir_temp,
            temp_files=temp_files,
        )

    def _cleanup_backup_job(self, job: _BackupJob) -> None:
        import invesalius.project as prj

        prj.CleanupSaveFiles(job.dir_temp, job.temp_files)
        # Left behind if the backup was cancelled before it started.
        self._remove_file(job.staging_path)

    @staticmethod
    def _remove_file(path: str) -> None:
        try:
            os.remove(path)
        except OSError:
            pass

    def CreateAutoBackup(self) -> bool:
        """
        Create (or overwrite) the auto-backup of the current project and wait
        until it is on disk.

        Used where the backup must be complete before returning (e.g. right after
        an image filter); regular changes use the background backup instead.
        Uses an atomic write pattern (write to a staging file, then os.replace)
        so a crash mid-write never corrupts the last good backup.
        Returns True if backup was created successfully.
        """
        # This backup includes every change so far, so drop scheduled ones, and let
        # a background backup finish first so it cannot overwrite this newer one.
        self._cancel_scheduled_backup()
        self._wait_backup_inflight()

        self._last_backup_time = time.monotonic()
        job = self._prepare_backup_job()
        if job is None:
            return False

        try:
            final_path = write_backup_archive(
                job.folder_name, job.files, job.staging_path, job.final_path
            )
        except Exception as e:
            debug(f"Failed to create auto-backup: {e}")
            return False
        finally:
            self._cleanup_backup_job(job)

        self._auto_backup_path = final_path
        self.SetState("auto_backup_path", final_path)
        debug(f"Auto-backup updated: {final_path}")
        return True

    def _cancel_scheduled_backup(self) -> None:
        if self._backup_timer is not None:
            self._backup_timer.Stop()
            self._backup_timer = None
        self._backup_pending = False
        self._backup_requested_time = None

    def RemoveAutoBackup(self) -> None:
        """Remove the auto-backup file if it exists."""
        # Discard backups that are scheduled or still being written.
        self._cancel_scheduled_backup()
        self._backup_generation += 1

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

    def _ShutdownBackup(self) -> None:
        """Stop scheduling backups, wait for the one being written and stop the worker."""
        self._cancel_scheduled_backup()
        self._wait_backup_inflight()
        self._shutdown_backup_executor(wait=True)

    def _Exit(self) -> None:
        self._ShutdownBackup()
        self.CloseProject()
        # Only delete state file if no unsaved changes (for crash recovery)
        if not self._has_unsaved_changes:
            self.DeleteStateFile()
