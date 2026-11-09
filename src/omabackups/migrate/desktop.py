"""Keybindings, bar & theme, on your side (D41-D43): after the root helper has
merged the files, the theme and background are applied through Omarchy's own
commands, and Hyprland is asked whether it accepts the merged files. If it
doesn't, they're put back as they were (your old ones kept to look at): a
Migrate never leaves a desktop with errors on it.
"""

import shutil
import subprocess
from pathlib import Path


def _run(*cmd: str) -> subprocess.CompletedProcess:
    if not shutil.which(cmd[0]):
        return subprocess.CompletedProcess(cmd, 127, "", "")
    return subprocess.run(cmd, capture_output=True, text=True)


def background(target: str, theme: str, from_user: str, home: Path) -> Path | None:
    """Where the old background is on this computer, if it's here."""
    if not target:
        return None
    name = Path(target).name
    old_home = f"/home/{from_user}" if from_user else ""
    candidates = []
    if old_home and target.startswith(old_home + "/"):
        candidates.append(home / target[len(old_home) + 1:])
    candidates += [home / ".config/omarchy/backgrounds" / theme / name,
                   home / ".local/state/omarchy/current/theme/backgrounds" / name]
    return next((c for c in candidates if c.is_file()), None)


def theme(found: dict, from_user: str, home: Path, say) -> list[dict]:
    name = (found or {}).get("name", "")
    if not name:
        return []
    done = _run("omarchy-theme-set", name)
    if done.returncode != 0:
        return [{"name": "Theme", "what": f"{name} isn't on this Omarchy: pick a theme in the menu."}]
    say(f"Theme: {name}.")
    picture = background(found.get("background", ""), name, from_user, home)
    if picture and _run("omarchy-theme-bg-set", str(picture)).returncode == 0:
        say(f"Background: {picture.name}.")
    elif found.get("background"):
        return [{"name": "Background", "what": "your old one isn't here; the theme's own is used."}]
    return []


def check_hyprland(merged: list[str], home: Path) -> list[dict]:
    """Hyprland must accept the merged files, or they go back as they were."""
    hypr = [m for m in merged if m.startswith(".config/hypr/")]
    if not hypr or not shutil.which("hyprctl"):
        return []
    _run("hyprctl", "reload")
    errors = _run("hyprctl", "configerrors").stdout.strip()
    if not errors:
        return []
    for rel in hypr:
        here, before = home / rel, home / (rel + ".omabackups-before")
        shutil.copy2(here, home / (rel + ".from-old-system"))
        if before.exists():
            shutil.copy2(before, here)
    _run("hyprctl", "reload")
    return [{"name": "Keybindings & Hyprland settings",
             "what": "didn't load on this Omarchy, so they were put back as they were. Your merged "
                     "files are kept next to them (*.from-old-system) to look at.", "details": errors}]


def apply(done: dict, from_user: str, say) -> list[dict]:
    home = Path.home()
    problems = check_hyprland(done.get("merged", []), home)
    problems += theme(done.get("theme", {}), from_user, home, say)
    return problems
