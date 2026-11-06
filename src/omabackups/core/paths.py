"""Every folder and file name OmaBackups uses, in one place.

All names are `omabackups`, so 2.0 never touches 1.x's `omarchy-backups` /
`oma-backups` folders (D23). Paths are worked out on every call (never cached
at import), so tests can point HOME and XDG_* somewhere else.
"""

import os
from pathlib import Path

APP = "omabackups"


def _xdg(var: str, fallback: str) -> Path:
    value = os.environ.get(var, "")
    # The XDG spec says relative values are invalid and must be ignored.
    if value and os.path.isabs(value):
        return Path(value)
    return Path.home() / fallback


# --- This user's files -------------------------------------------------------

def config_dir() -> Path:
    return _xdg("XDG_CONFIG_HOME", ".config") / APP


def settings_file() -> Path:
    return config_dir() / "settings.toml"


def state_dir() -> Path:
    return _xdg("XDG_STATE_HOME", ".local/state") / APP


def state_file(name: str) -> Path:
    if not name or "/" in name or name.startswith("."):
        raise ValueError(f"bad state file name: {name!r}")
    return state_dir() / f"{name}.json"


def log_dir() -> Path:
    return state_dir() / "logs"


def log_file() -> Path:
    return log_dir() / "omabackups.log"


def cache_dir() -> Path:
    return _xdg("XDG_CACHE_HOME", ".cache") / APP


def runtime_dir() -> Path:
    value = os.environ.get("XDG_RUNTIME_DIR", "")
    if value and os.path.isabs(value):
        return Path(value) / APP
    return cache_dir() / "run"


# --- System files (owned by the package or the root helper) -----------------
# OMABACKUPS_SYSROOT moves these under a test folder; it is never set in use.

def _sys(path: str) -> Path:
    root = os.environ.get("OMABACKUPS_SYSROOT", "")
    return Path(root + path) if root else Path(path)


def system_config_dir() -> Path:
    return _sys("/etc/omabackups")


def system_state_dir() -> Path:
    return _sys("/var/lib/omabackups")


def system_run_dir() -> Path:
    return _sys("/run/omabackups")


def machine_id_file() -> Path:
    return _sys("/etc/machine-id")
