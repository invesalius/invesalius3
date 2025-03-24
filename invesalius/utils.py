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
import atexit
import collections.abc
import locale
import logging
import math
import os
import platform
import queue
import re
import shutil
import sys
import tempfile
import threading
import time
import traceback
import weakref
from concurrent.futures import ThreadPoolExecutor
from functools import wraps
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np
from packaging.version import Version

import invesalius

# Configure logger for temp file management
logger = logging.getLogger("invesalius.temp_manager")
logger.setLevel(logging.DEBUG)

# Create console handler with a higher log level
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

# Create formatter and add it to the handler
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
console_handler.setFormatter(formatter)

# Add the handler to the logger
logger.addHandler(console_handler)


def format_time(value: str) -> str:
    sp1 = value.split(".")
    sp2 = value.split(":")

    if (len(sp1) == 2) and (len(sp2) == 3):
        new_value = str(sp2[0] + sp2[1] + str(int(float(sp2[2]))))
        data = time.strptime(new_value, "%H%M%S")
    elif len(sp1) == 2:
        data = time.gmtime(float(value))
    elif len(sp1) > 2:
        data = time.strptime(value, "%H.%M.%S")
    elif len(sp2) > 1:
        data = time.strptime(value, "%H:%M:%S")
    else:
        try:
            data = time.strptime(value, "%H%M%S")
        # If the time is not in a bad format only return it.
        except ValueError:
            return value
    return time.strftime("%H:%M:%S", data)


def format_date(value: str) -> str:
    sp1 = value.split(".")
    try:
        if len(sp1) > 1:
            if len(sp1[0]) <= 2:
                data = time.strptime(value, "%d.%m.%Y")
            else:
                data = time.strptime(value, "%Y.%m.%d")
        elif len(value.split("//")) > 1:
            data = time.strptime(value, "%d/%m/%Y")
        else:
            data = time.strptime(value, "%Y%m%d")
        return time.strftime("%d/%m/%Y", data)

    except ValueError:
        return ""


def debug(error_str: str) -> None:
    """
    Redirects output to file, or to the terminal
    This should be used in the place of "print"
    """
    from invesalius.session import Session

    session = Session()
    if session.GetConfig("debug"):
        print(error_str)


def next_copy_name(original_name: str, names_list: List[str]) -> str:
    """
    Given original_name of an item and a list of existing names,
    builds up the name of a copy, keeping the pattern:
        original_name
        original_name copy
        original_name copy#1
    """
    # is there only one copy, unnumbered?
    if original_name.endswith(" copy"):
        first_copy = original_name
        last_index = -1
    else:
        parts = original_name.rpartition(" copy#")
        # is there any copy, might be numbered?
        if parts[0] and parts[-1]:
            # yes, lets check if it ends with a number
            if isinstance(eval(parts[-1]), int):
                last_index = int(parts[-1]) - 1
                first_copy = f"{parts[0]} copy"
            # no... well, so will build the copy name from zero
            else:
                last_index = -1
                first_copy = f"{original_name} copy"
                # apparently this isthe new copy name, check it
                if first_copy not in names_list:
                    return first_copy

        else:
            # no, apparently there are no copies, as
            # separator was not found -- returned ("", " copy#", "")
            last_index = -1
            first_copy = f"{original_name} copy"

            # apparently this isthe new copy name, check it
            if first_copy not in names_list:
                return first_copy

    # lets build up the new name based on last pattern value
    got_new_name = False
    while not got_new_name:
        last_index += 1
        next_copy = "%s#%d" % (first_copy, last_index + 1)
        if next_copy not in names_list:
            got_new_name = True
    return next_copy


def new_name_by_pattern(pattern: str) -> str:
    from invesalius.project import Project

    proj = Project()
    mask_dict = proj.mask_dict
    names_list = [i.name for i in mask_dict.values() if i.name.startswith(pattern + "_")]
    count = len(names_list) + 1
    return f"{pattern}_{count}"


def VerifyInvalidPListCharacter(text: str) -> bool:
    # print text
    # text = unicode(text)

    _controlCharPat = re.compile(
        r"[\x00\x01\x02\x03\x04\x05\x06\x07\x08\x0b\x0c\x0e\x0f"
        r"\x10\x11\x12\x13\x14\x15\x16\x17\x18\x19\x1a\x1b\x1c\x1d\x1e\x1f]"
    )
    m = _controlCharPat.search(text)

    if m is not None:
        return True
    else:
        return False


# http://www.garyrobinson.net/2004/03/python_singleto.html
# Gary Robinson
class Singleton(type):
    def __init__(cls, name, bases, dic):
        super().__init__(name, bases, dic)
        cls.instance = None

    def __call__(cls, *args, **kw):
        if cls.instance is None:
            cls.instance = super().__call__(*args, **kw)
        return cls.instance


# Another possible implementation
# class Singleton(object):
#   def __new__(cls, *args, **kwargs):
#      if '_inst' not in vars(cls):
#         cls._inst = type.__new__(cls, *args, **kwargs)
#      return cls._inst


class TwoWaysDictionary(dict):
    """
    Dictionary that can be searched based on a key or on a item.
    The idea is to be able to search for the key given the item it maps.
    """

    def __init__(self, items=[]):
        dict.__init__(self, items)

    def get_key(self, value):
        """
        Find the key (first) with the given value
        """
        keys = self.get_keys(value)
        return keys[0] if keys else None

    def get_keys(self, value):
        """
        Find the key(s) as a list given a value.
        """
        return [item[0] for item in self.items() if item[1] == value]

    def remove(self, key):
        try:
            self.pop(key)
        except KeyError:
            debug("TwoWaysDictionary: key not found")

    def get_value(self, key):
        """
        Find the value given a key.
        """
        return self.get(key, None)


# DEPRECATED
def frange(start: float, end: Optional[float] = None, inc: Optional[float] = None) -> List[float]:
    "A range function, that accepts float increments."

    if end is None:
        end = start + 0.0
        start = 0.0

    if (inc is None) or (inc == 0):
        inc = 1.0

    L: List[float] = []
    while 1:
        next = start + len(L) * inc
        if inc > 0 and next >= end:
            break
        elif inc < 0 and next <= end:
            break
        L.append(next)

    return L


# Deprecated
def calculate_resizing_tofitmemory(x_size, y_size, n_slices, byte):
    """
    Predicts the percentage (between 0 and 1) to resize the image to fit the memory,
    giving the following information:
        x_size, y_size: image size
        n_slices: number of slices
        byte: bytes allocated for each pixel sample
    """
    imagesize = x_size * y_size * n_slices * byte * 28

    #  USING LIBSIGAR
    # import sigar
    # sg = sigar.open()
    # ram_free = sg.mem().actual_free()
    # ram_total = sg.mem().total()
    # swap_free = sg.swap().free()
    # sg.close()

    # USING PSUTIL
    import psutil

    try:
        if psutil.version_info >= (0, 6, 0):
            ram_free = psutil.virtual_memory().available
            ram_total = psutil.virtual_memory().total
            swap_free = psutil.swap_memory().free
        else:
            ram_free = psutil.phymem_usage().free + psutil.cached_phymem() + psutil.phymem_buffers()
            ram_total = psutil.phymem_usage().total
            swap_free = psutil.virtmem_usage().free
    except Exception:
        print("Exception! psutil version < 0.3 (not recommended)")
        ram_total = psutil.TOTAL_PHYMEM  # this is for psutil < 0.3
        ram_free = 0.8 * psutil.TOTAL_PHYMEM
        swap_free = psutil.avail_virtmem()

    print("RAM_FREE=", ram_free)
    print("RAM_TOTAL=", ram_total)

    if sys.platform == "win32":
        if platform.architecture()[0] == "32bit":
            if ram_free > 1400000000:
                ram_free = 1400000000
            if ram_total > 1400000000:
                ram_total = 1400000000

    if sys.platform.startswith("linux"):
        if platform.architecture()[0] == "32bit":
            if ram_free > 3500000000:
                ram_free = 3500000000
            if ram_total > 3500000000:
                ram_total = 3500000000

    if swap_free > ram_total:
        swap_free = ram_total
    resize = float((ram_free + 0.5 * swap_free) / imagesize)
    resize = math.sqrt(resize)  # this gives the "resize" for each axis x and y
    if resize > 1:
        resize = 1
    return round(resize, 2)


def get_system_encoding() -> Optional[str]:
    if sys.platform == "win32":
        return locale.getdefaultlocale()[1]
    else:
        return "utf-8"


def UpdateCheck() -> None:
    import requests
    import wx

    import invesalius.session as ses

    def _show_update_info():
        from invesalius.gui import dialogs
        # from invesalius.i18n import tr as _

        # msg = _(
        #     "A new version of InVesalius is available. Do you want to open the download website now?"
        # )
        # title = _("Invesalius Update")
        msgdlg = dialogs.UpdateMessageDialog(url)
        # if (msgdlg.Show()==wx.ID_YES):
        # wx.LaunchDefaultBrowser(url)
        msgdlg.Show()
        # msgdlg.Destroy()

    print("Checking updates...")

    # Check if a language has been set.
    session = ses.Session()
    lang = session.GetConfig("language")
    random_id = session.GetConfig("random_id")

    if lang:
        # Fetch update data from server
        import invesalius.constants as const

        url = "https://www.cti.gov.br/dt3d/invesalius/update/checkupdate.php"
        data: Any = {
            "update_protocol_version": "1",
            "invesalius_version": invesalius.__version__,
            "platform": sys.platform,
            "architecture": platform.architecture()[0],
            "language": lang,
            "random_id": random_id,
        }
        response = requests.post(url, data=data, verify=False)
        last, url = response.text.split()

        try:
            last_ver = Version(last)
            actual_ver = Version(invesalius.__version__)
        except (ValueError, AttributeError):
            return

        if last_ver > actual_ver:
            print("  ...New update found!!! -> version:", last)
            wx.CallAfter(wx.CallLater, 1000, _show_update_info)


def vtkarray_to_numpy(m):
    nm = np.zeros((4, 4))
    for i in range(4):
        for j in range(4):
            nm[i, j] = m.GetElement(i, j)
    return nm


def touch(fname: str) -> None:
    with open(fname, "a"):
        pass


def decode(text: Any, encoding: str, *args) -> Any:
    try:
        return text.decode(encoding, *args)
    except AttributeError:
        return text


def encode(text: Any, encoding: str, *args) -> Any:
    try:
        return text.encode(encoding, *args)
    except AttributeError:
        return text


def timing(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = f(*args, **kwargs)
        end = time.time()
        print(f"{f.__name__} elapsed time: {end - start}")
        return result

    return wrapper


def log_traceback(ex: Any) -> str:
    if hasattr(ex, "__traceback__"):
        ex_traceback = ex.__traceback__
    else:
        _, _, ex_traceback = sys.exc_info()
    tb_lines = [
        line.rstrip("\n") for line in traceback.format_exception(ex.__class__, ex, ex_traceback)
    ]
    return "".join(tb_lines)


def deep_merge_dict(d, u):
    for k, v in u.items():
        if isinstance(v, collections.abc.Mapping):
            d[k] = deep_merge_dict(d.get(k, {}), v)
        else:
            d[k] = v
    return d


class TempFileManager(metaclass=Singleton):
    """
    A singleton class that manages temporary files in the application.
    Handles safe cleanup of temporary files that are no longer in use.
    Uses thread pool for parallel file operations.
    """

    def __init__(self):
        self._temp_files: Dict[
            str, Dict[str, Any]
        ] = {}  # path -> {refs: int, last_access: float, is_dir: bool}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=4)  # Thread pool for file operations
        self._cleanup_queue = queue.Queue()
        self._cleanup_thread = threading.Thread(target=self._cleanup_worker, daemon=True)
        self._cleanup_thread.start()
        self._is_shutting_down = False
        self._ignored_files = set()  # Files we've tried to delete but failed
        atexit.register(self.shutdown)  # Register shutdown handler

        # Start background cleanup of old VTP files
        self._start_background_vtp_cleanup()

        logger.info("TempFileManager initialized")

    def _start_background_vtp_cleanup(self) -> None:
        """Start background thread to clean up old VTP files."""

        def cleanup_thread():
            try:
                self._cleanup_old_vtp_files()
            except Exception as e:
                logger.error(f"Error in VTP cleanup thread: {str(e)}")

        # Start cleanup in background thread
        cleanup_thread = threading.Thread(target=cleanup_thread, daemon=True)
        cleanup_thread.start()

    def _cleanup_old_vtp_files(self) -> None:
        """Clean up any VTP files left from previous sessions."""
        temp_dir = tempfile.gettempdir()

        # Patterns for different types of VTP files
        vtp_patterns = [
            os.path.join(temp_dir, "tmp*_full.vtp"),  # Final combined surfaces
            os.path.join(temp_dir, "tmp*_*_*.vtp"),  # Surface pieces
            os.path.join(temp_dir, "tmp[a-z0-9_]*"),
            os.path.join(temp_dir, "tmp*[0-9]"),
        ]

        try:
            import glob

            old_vtp_files = []

            # Collect all matching VTP files
            for pattern in vtp_patterns:
                old_vtp_files.extend(glob.glob(pattern))

            if old_vtp_files:
                logger.info(f"Found {len(old_vtp_files)} leftover VTP files from previous session")

                for vtp_file in old_vtp_files:
                    try:
                        # Check if file is older than 1 hour
                        if time.time() - os.path.getmtime(vtp_file) > 60:
                            # Register and immediately queue for cleanup using existing infrastructure
                            self.register_temp_file(vtp_file, ref_count=0)
                            self._cleanup_queue.put(vtp_file)
                            logger.debug(f"Queued old temp file for cleanup: {vtp_file}")
                    except (OSError, IOError) as e:
                        logger.warning(f"Could not process old VTP file {vtp_file}: {str(e)}")

        except Exception as e:
            logger.error(f"Error during old VTP file cleanup: {str(e)}")

    def register_temp_file(self, file_path: str, ref_count: int = 1) -> None:
        """
        Register a temporary file or directory with the manager.

        Args:
            file_path: Path to the temporary file or directory
            ref_count: Initial reference count (default: 1)
        """
        if not file_path:
            return

        with self._lock:
            if file_path in self._temp_files:
                self._temp_files[file_path]["refs"] += ref_count
                logger.debug(
                    f"Increased ref count for {file_path} by {ref_count} (total: {self._temp_files[file_path]['refs']})"
                )
            else:
                self._temp_files[file_path] = {
                    "refs": ref_count,
                    "last_access": time.monotonic(),
                    "is_dir": os.path.isdir(file_path),
                }
                logger.info(
                    f"Registered new temp {'directory' if os.path.isdir(file_path) else 'file'}: {file_path} with ref count {ref_count}"
                )

    def increment_refs(self, file_path: str) -> None:
        """Increment reference count for a temporary file or directory."""
        if not file_path:
            return

        with self._lock:
            if file_path in self._temp_files:
                self._temp_files[file_path]["refs"] += 1
                self._temp_files[file_path]["last_access"] = time.monotonic()
                logger.debug(
                    f"Incremented ref count for {file_path} (total: {self._temp_files[file_path]['refs']})"
                )

    def decrement_refs(self, file_path: str) -> None:
        """Decrement reference count for a temporary file or directory."""
        if not file_path:
            return

        with self._lock:
            if file_path in self._temp_files:
                self._temp_files[file_path]["refs"] -= 1
                logger.debug(
                    f"Decremented ref count for {file_path} (remaining: {self._temp_files[file_path]['refs']})"
                )

                # Only queue for cleanup if refs reached 0 and file is still in our tracking
                if self._temp_files[file_path]["refs"] <= 0:
                    if file_path in self._temp_files:  # Double-check within lock
                        logger.info(f"Queuing {file_path} for cleanup (ref count reached 0)")
                        self._cleanup_queue.put(file_path)
                        # Remove from tracking immediately to prevent duplicate cleanup attempts
                        self._temp_files.pop(file_path, None)

    def _cleanup_worker(self) -> None:
        """Background worker that handles file cleanup."""
        logger.info("Cleanup worker thread started")
        while True:
            try:
                file_path = self._cleanup_queue.get()
                if file_path is None:  # Shutdown signal
                    logger.info("Cleanup worker received shutdown signal")
                    break

                logger.debug(f"Submitting cleanup task for {file_path}")
                self._executor.submit(self._safe_remove_file, file_path)
                self._cleanup_queue.task_done()
            except Exception as e:
                logger.error(f"Error in cleanup worker: {str(e)}")

    def _safe_remove_file(self, file_path: str) -> None:
        """Safely remove a file or directory, handling various edge cases."""
        if not file_path or file_path in self._ignored_files:
            return

        try:
            if os.path.exists(file_path):
                # Try to remove the file or directory
                logger.debug(f"Attempting to remove {file_path}")

                # On Windows, try to ensure the file is not in use
                if sys.platform == "win32":
                    import gc

                    gc.collect()  # Force garbage collection to close any lingering file handles

                if os.path.isdir(file_path):
                    shutil.rmtree(file_path)
                    logger.info(f"Successfully removed temp directory: {file_path}")
                else:
                    os.remove(file_path)
                    logger.info(f"Successfully removed temp file: {file_path}")

                with self._lock:
                    self._temp_files.pop(file_path, None)

            else:
                # File/directory doesn't exist, remove from tracking
                with self._lock:
                    self._temp_files.pop(file_path, None)

        except (OSError, IOError) as e:
            logger.warning(
                f"Could not remove temp {'directory' if os.path.isdir(file_path) else 'file'} {file_path}, will be cleaned up by OS: {str(e)}"
            )
            with self._lock:
                self._ignored_files.add(file_path)
                self._temp_files.pop(file_path, None)

    def cleanup_all(self) -> None:
        """Clean up all registered temporary files and directories."""
        with self._lock:
            files_to_remove = list(self._temp_files.keys())

        logger.info(
            f"Cleaning up all temp files/directories ({len(files_to_remove)} items, {len(self._ignored_files)} ignored)"
        )

        for file_path in files_to_remove:
            if file_path not in self._ignored_files:
                self._cleanup_queue.put(file_path)

        # Wait for all cleanup operations to complete
        self._cleanup_queue.join()
        logger.info("Completed cleanup of all temp files and directories")

    def shutdown(self) -> None:
        """Shutdown the temp file manager and cleanup resources."""
        with self._lock:
            if self._is_shutting_down:
                return
            self._is_shutting_down = True
            logger.info("Initiating TempFileManager shutdown")
            try:
                self._cleanup_queue.put(None)  # Signal cleanup worker to stop
                self._cleanup_thread.join(timeout=5)  # Wait up to 5 seconds for thread to stop
                self._executor.shutdown(wait=True)
                self.cleanup_all()
                logger.info("TempFileManager shutdown completed successfully")
            except Exception as e:
                logger.error(f"Error during TempFileManager shutdown: {str(e)}")
