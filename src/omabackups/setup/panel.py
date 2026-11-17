"""Take OmaBackups' panel off the bar (D55): the last step of Remove
OmaBackups, as 1.x's uninstall.sh did. The panel without the `omabackups`
command makes no sense; the command without the panel still does, so
removing only the panel stays allowed.

The shell switches the plugin off, its folder goes (a linked folder is only
unlinked, never followed), and the shell looks again."""

import shutil
import subprocess
from pathlib import Path

PLUGIN = "omabackups"


def folder() -> Path:
    """Where Omarchy keeps shell plugins (fixed there, as its own
    omarchy-plugin-remove has it)."""
    return Path.home() / ".config" / "omarchy" / "plugins" / PLUGIN


def remove() -> bool:
    """True when there was a panel to take away."""
    target = folder()
    there = target.is_symlink() or target.exists()
    _shell("setPluginEnabled", PLUGIN, "false")
    if target.is_symlink():
        target.unlink()
    elif target.exists():
        shutil.rmtree(target, ignore_errors=True)
    _shell("rescanPlugins")
    return there


def _shell(*args: str) -> None:
    """Best effort: without a running shell there's nothing on the bar to
    switch off."""
    if not shutil.which("omarchy-shell"):
        return
    subprocess.run(["omarchy-shell", "shell", *args], capture_output=True, timeout=20, check=False)
