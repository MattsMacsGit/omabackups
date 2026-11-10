"""Run the audit: "Your changes to Omarchy" (D9), at every backup, as root.

Reads this computer as it is (packages, configs, system files) for the
linked user; writes nothing. Sizes are measured within a time limit; folders
in your home are listed without sizes (Migrate takes those from the backup:
1.x lesson, never from the disk when the question is the backup).
"""

import json
import os
import pwd
import subprocess
import time
from pathlib import Path

from omabackups.audit import extras, model, omarchy, packages, tools, tweaks
from omabackups.audit.model import item
from omabackups.core import log

KNOWN = Path(__file__).with_name("known.json")
SIZE_BUDGET = 20.0       # seconds for measuring folders, at most


class Sizer:
    def __init__(self, budget: float):
        self.until = time.monotonic() + budget

    def size(self, paths: list[str], finder) -> int | None:
        total = 0
        for p in paths:
            if time.monotonic() > self.until:
                return None
            try:
                out = subprocess.run(["du", "-sxb", "--", str(finder.expand(p))], capture_output=True,
                                     text=True, timeout=max(1, self.until - time.monotonic())).stdout
                total += int(out.split()[0])
            except (OSError, subprocess.TimeoutExpired, IndexError, ValueError):
                return None
        return total


def settings(known: dict, finder) -> list[dict]:
    out = []
    for s in known.get("settings", []):
        paths = [finder.expand(p) for p in s["paths"] if finder.expand(p).exists()]
        if not paths:
            continue
        finder.claim(paths)
        out.append(item(f"setting:{s['id']}", "settings", s["name"], "folder", [s["id"]],
                        [finder.tilde(p) for p in paths], s["suggest"], float(s.get("weight", 50)),
                        s.get("what", ""), s.get("why", ""), "it isn't anywhere else",
                        merge=bool(s.get("merge")), skip_under=s.get("skip_under", [])))
    return out


def home_folders(home: Path, known: dict, finder) -> list[dict]:
    """Your files (visible folders) and the known hidden ones."""
    out = []
    for p in sorted(home.iterdir()) if home.is_dir() else []:
        if p.name.startswith(".") or not p.is_dir() or p.is_symlink():
            continue
        out.append(item(f"files:{p.name}", "files", p.name, "folder", [p.name], [finder.tilde(p)],
                        "keep", 40, "A folder in your home.", "your own files",
                        "they're only in your backup"))
    for name, h in known.get("hidden", {}).items():
        p = home / name
        if h.get("skip") or not p.exists() or p in finder.claimed:
            continue
        out.append(item(f"hidden:{name}", "settings", h.get("name", name), "folder", [name],
                        [finder.tilde(p)], h.get("suggest", "you"), 15, "", h.get("why", ""),
                        "downloaded again when needed" if h.get("suggest") == "leave" else ""))
    return out


def scan(user: str | None = None) -> dict:
    started = time.monotonic()
    if os.environ.get("OMABACKUPS_SYSROOT"):      # tests: the sandbox's home, never the real one
        home, user = Path.home(), user or "test"
    elif user:
        home = Path(pwd.getpwnam(user).pw_dir)
    else:
        home, user = Path.home(), pwd.getpwuid(os.getuid()).pw_name
    known = json.loads(KNOWN.read_text())
    finder = packages.Finder(home, set(known.get("shared_dirs", [])))
    found = settings(known, finder)              # first: a browser profile is a setting
    apps, notes = packages.packages(home, known, finder)
    found += apps + packages.flatpaks(user, known, finder) + omarchy.webapps(home)
    found += tools.tools(user, home)
    found += omarchy.desktop(home, finder.claimed) + extras.extras(home, user, finder)    # D46
    found += tweaks.tweaks() + home_folders(home, known, finder)
    sizer = Sizer(SIZE_BUDGET)
    for i in found:
        if i["group"] != "files" and i["paths"]:
            i["bytes"] = sizer.size(i["paths"], finder)
    notes["seconds"] = round(time.monotonic() - started, 1)
    return model.audit({"system": "omarchy", "version": omarchy.version()}, user, found, notes)


def safely(user: str | None) -> dict | None:
    """For the backup: an audit problem is logged, never a failed backup."""
    try:
        return scan(user)
    except Exception as exc:  # noqa: BLE001
        log.get("audit").warning("the audit didn't finish: %r %s", exc, getattr(exc, "filename", "") or "",
                                 exc_info=True)
        return None
