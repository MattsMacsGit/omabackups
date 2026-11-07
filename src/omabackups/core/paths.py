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


def linked_user_file() -> Path:
    """Which user this computer's OmaBackups belongs to (D27)."""
    return system_config_dir() / "user.json"


def server_file() -> Path:
    """The backup server this computer backs up to (written after setup succeeded)."""
    return system_config_dir() / "server.json"


def keys_dir() -> Path:
    """Root-only: the SSH key for the backup server, and the backup's unlock key."""
    return system_state_dir() / "keys"


def known_hosts_file() -> Path:
    return system_state_dir() / "known_hosts"


def requests_dir() -> Path:
    """Where this user leaves inputs for root jobs (D27): the user's own
    private runtime folder, so no group membership is needed."""
    return runtime_dir() / "requests"


def user_requests_location(uid: int) -> tuple[Path, list[str]]:
    """The linked user's request folder as root walks to it: a starting
    folder owned by that user, then the parts below it (each checked)."""
    if os.environ.get("OMABACKUPS_SYSROOT"):   # tests: the sandbox's own
        return runtime_dir(), ["requests"]
    return Path(f"/run/user/{uid}"), [APP, "requests"]


def polkit_rule_file() -> Path:
    """Written by `link` (D27): lets only the linked user start our root jobs."""
    return _sys("/etc/polkit-1/rules.d/50-omabackups.rules")


def results_dir() -> Path:
    return system_run_dir() / "results"


def gate_bundle() -> Path:
    """The gatekeeper, packed into one file by the package."""
    return _sys("/usr/share/omabackups/gate.pyz")


SERVER_ALIAS = "omabackups-server"   # the name SSH files the server's host key under
