"""
shortcut_manager.py
-------------------
Central registry for InVesalius keyboard shortcuts.

Usage
-----
    from invesalius.gui.shortcut_manager import ShortcutManager
    sm = ShortcutManager()          # loads on first call, cached after
    label = sm.get_menu_label("import_dicom", "Import DICOM")
    # returns e.g. "Import DICOM\tCtrl+I"

    sm.set_shortcut("import_dicom", "Ctrl+Shift+I")
    sm.save()
"""

import json
import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# The bundled default lives next to this file (invesalius/gui/shortcuts.json).
_DEFAULT_JSON = Path(__file__).parent / "shortcuts.json"


# The user-editable copy lives in the InVesalius config directory so it
# survives reinstalls.  We import inv_paths lazily to avoid circular imports.
def _user_json_path() -> Path:
    from invesalius import inv_paths  # noqa: PLC0415

    return Path(inv_paths.USER_INV_DIR) / "shortcuts.json"


# ---------------------------------------------------------------------------
# ShortcutManager
# ---------------------------------------------------------------------------


class ShortcutManager:
    """
    Singleton-style manager for keyboard shortcuts.

    Call ``ShortcutManager()`` anywhere; the first call loads the JSON,
    subsequent calls return the same cached instance.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            obj = super().__new__(cls)
            obj._shortcuts = {}  # action_id -> dict entry from JSON
            obj._loaded = False
            cls._instance = obj
        return cls._instance

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self) -> None:
        """
        Load shortcuts from the user config file.
        If no user file exists yet, copy the bundled default there first.
        """
        user_path = _user_json_path()

        if not user_path.exists():
            self._seed_user_file(user_path)

        try:
            with open(user_path, encoding="utf-8") as fh:
                data = json.load(fh)
            self._shortcuts = {entry["action_id"]: entry for entry in data.get("shortcuts", [])}
        except Exception as exc:
            logger.error(f"Failed to load {user_path}: {exc}")
            logger.info("Falling back to bundled defaults.")
            self._load_defaults()

        self._loaded = True

    def save(self) -> None:
        """Persist the current (possibly edited) shortcuts to the user file."""
        user_path = _user_json_path()
        user_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "_comment": (
                "InVesalius keyboard shortcuts registry. "
                "Edit 'current' to remap. Do not change 'action_id' or 'category'."
            ),
            "shortcuts": list(self._shortcuts.values()),
        }
        try:
            with open(user_path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=False)
        except Exception as exc:
            logger.error(f"Failed to save shortcuts: {exc}")

    def reset_all(self) -> None:
        """Reset every shortcut to its factory default and save."""
        for entry in self._shortcuts.values():
            entry["current"] = entry["default"]
        self.save()

    def reset_one(self, action_id: str) -> None:
        """Reset a single shortcut to its factory default."""
        if action_id in self._shortcuts:
            entry = self._shortcuts[action_id]
            entry["current"] = entry["default"]

    def get_shortcut(self, action_id: str) -> str:
        """Return the *current* key string for action_id, e.g. 'Ctrl+I'."""
        self._ensure_loaded()
        entry = self._shortcuts.get(action_id)
        if entry is None:
            return ""
        return entry.get("current") or entry.get("default", "")

    def set_shortcut(self, action_id: str, key_string: str) -> None:
        """
        Update the current binding for action_id.
        Raises ValueError if key_string conflicts with another action.
        Does NOT save automatically — call save() when done.
        """
        self._ensure_loaded()
        conflict = self._find_conflict(action_id, key_string)
        if conflict:
            raise ValueError(f"Key '{key_string}' is already used by '{conflict}'.")
        if action_id in self._shortcuts:
            self._shortcuts[action_id]["current"] = key_string

    def get_menu_label(self, action_id: str, base_label: str) -> str:
        """
        Build the full wxPython menu label string.

        Example:
            get_menu_label("import_dicom", "Import DICOM")
            -> "Import DICOM\\tCtrl+I"

        If the action has no shortcut, returns base_label unchanged.
        """
        key = self.get_shortcut(action_id)
        if key:
            return f"{base_label}\t{key}"
        return base_label

    def all_shortcuts(self) -> list:
        """Return a list of all shortcut dicts (sorted by category then label)."""
        self._ensure_loaded()
        return sorted(
            self._shortcuts.values(),
            key=lambda e: (e.get("category", ""), e.get("label", "")),
        )

    def find_action_by_key(self, key_string: str) -> str | None:
        """Return the action_id that currently uses key_string, or None."""
        self._ensure_loaded()
        for action_id, entry in self._shortcuts.items():
            if entry.get("current", "").lower() == key_string.lower():
                return action_id
        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    def _seed_user_file(self, user_path: Path) -> None:
        """Copy the bundled shortcuts.json to the user config directory."""
        user_path.parent.mkdir(parents=True, exist_ok=True)
        if _DEFAULT_JSON.exists():
            shutil.copy2(_DEFAULT_JSON, user_path)
        else:
            # Bundled file missing — write a minimal valid JSON so we don't crash.
            logger.warning("Bundled shortcuts.json not found; creating empty user file.")
            with open(user_path, "w", encoding="utf-8") as fh:
                json.dump({"shortcuts": []}, fh, indent=2)

    def _load_defaults(self) -> None:
        """Load directly from the bundled default file (fallback)."""
        try:
            with open(_DEFAULT_JSON, encoding="utf-8") as fh:
                data = json.load(fh)
            self._shortcuts = {entry["action_id"]: entry for entry in data.get("shortcuts", [])}
        except Exception as exc:
            logger.critical(f"Cannot load bundled defaults either: {exc}")
            self._shortcuts = {}

    def _find_conflict(self, action_id: str, key_string: str) -> str | None:
        """
        Return the label of the action that already uses key_string,
        or None if there is no conflict.
        Ignores the action_id being reassigned (so you can 're-set' to same key).
        """
        if not key_string:
            return None
        for aid, entry in self._shortcuts.items():
            if aid == action_id:
                continue
            if entry.get("current", "").lower() == key_string.lower():
                return entry.get("label", aid)
        return None
