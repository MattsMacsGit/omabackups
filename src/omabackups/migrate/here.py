"""What's on this computer already (D44 part 2): Run Migrate again shows it
as "Already in".

- An app: installed here (pacman, Flatpak, or the tool's command found).
- Settings and System tweaks: nearly all their files (9 in 10) are here with
  the backup's size and time (what copying keeps). Not every one: an app
  rewrites a few of its own files each time it runs (Chromium), and folders
  named after the old home folder get the new name. Changed since, or a
  fresh install's own file instead of yours: not in.
- An app with settings: installed AND its settings here. An app you log in
  to (Tailscale): installed and logged in is enough (its state file
  keeps changing: that's it working).
- Shell history: in when it has the past in it, the backup's last commands
  (if it has the past it came over; if it only has what's been typed since,
  it was blank). It keeps growing, so its size and time never match.
Folders (Your files) are left to Restore my files' own record.

The root side lists the restore point against this computer with a dry run
of rsync (nothing is copied); tally() reads that listing.
"""

import shutil
import subprocess

# rsync's dry run: every file listed, changed or not (-ii); no owners or
# permissions compared (they're this computer's own).
DRY_RUN = ["rsync", "-rlt", "-n", "-ii", "--out-format=%i %l %n"]
SHARE = 0.9
# Files that keep growing once they're back: in when they have the past.
HISTORY = {".bash_history", ".zsh_history", ".local/share/fish/fish_history"}
# Apps you log in to: in when installed and this says logged in (exit 0).
LOGGED_IN = {"tailscale": ["tailscale", "status"]}


def has_past(old: str, here: str, last: int = 20) -> bool:
    """The backup's history is in this one: its last commands, in order."""
    tail = [x for x in old.splitlines() if x.strip()][-last:]
    if not tail:
        return False
    lines = here.splitlines()
    return any(lines[k:k + len(tail)] == tail for k in range(len(lines) - len(tail) + 1))


def histories(listing: str) -> list[str]:
    """The history files that differ from the backup's (to look inside)."""
    return [line[12:].partition(" ")[2] for line in listing.splitlines()
            if line[:1] in "><c" and line[12:].partition(" ")[2] in HISTORY]


def tally(listing: str, items: list[str], kept: set[str] = frozenset()) -> set[str]:
    """The items (paths relative to the part) whose files are nearly all here.
    kept: files that count as here although they differ (a history with the past)."""
    total = {i: 0 for i in items}
    same = {i: 0 for i in items}
    for line in listing.splitlines():
        flags, rest = line[:11], line[12:]          # %i is 11 characters wide, then a space
        _size, _, name = rest.partition(" ")
        if len(flags) < 2 or flags[1] not in "fL" or not name:
            continue
        owner = next((i for i in items if name == i or name.startswith(i.rstrip("/") + "/")), None)
        if owner is None:
            continue
        total[owner] += 1
        if flags[0] not in "><c*" or name in kept:
            same[owner] += 1
    return {i for i in items if total[i] and same[i] >= SHARE * total[i]}


def _installed() -> tuple[set[str], set[str]]:
    def lines(cmd):
        if not shutil.which(cmd[0]):
            return set()
        try:
            return set(subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout.split())
        except (OSError, subprocess.TimeoutExpired):
            return set()
    return lines(["pacman", "-Qq"]), lines(["flatpak", "list", "--app", "--columns=application"])


def _ok(cmd: list[str]) -> bool:
    if not shutil.which(cmd[0]):
        return False
    try:
        return subprocess.run(cmd, capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def asked(changes: dict) -> tuple[list[str], list[str]]:
    """The settings and tweaks to look for: (home items, system items)."""
    home, system = [], []
    for it in changes.get("items", []):
        if it.get("group") == "files":
            continue
        for p in it.get("paths", []):
            if p.startswith("~/"):
                home.append(p[2:])
            elif p.startswith("/"):
                system.append(p.lstrip("/"))
    return sorted(set(home)), sorted(set(system))


def found(changes: dict, home_in: set[str], system_in: set[str], installed=None) -> set[str]:
    """The rows already on this computer."""
    packages, flatpaks = installed if installed is not None else _installed()
    out = set()
    for it in changes.get("items", []):
        if it.get("group") == "files":
            continue
        src = it.get("source", {})
        kind, refs = src.get("kind"), src.get("refs", [])
        if kind == "package" and not (refs and all(r in packages for r in refs)):
            continue
        if kind == "flatpak" and not (refs and all(r in flatpaks for r in refs)):
            continue
        if kind == "tool" and not shutil.which((refs or [it.get("name", "")])[0]):
            continue
        if kind == "package" and any(r in LOGGED_IN and _ok(LOGGED_IN[r]) for r in refs):
            out.add(it["id"])
            continue
        paths = it.get("paths", [])
        if not paths and kind not in ("package", "flatpak", "tool"):
            continue
        if all(p[2:] in home_in if p.startswith("~/") else p.lstrip("/") in system_in for p in paths):
            out.add(it["id"])
    return out
