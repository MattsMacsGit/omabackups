"""Never send the same data twice (D25, 1.x's reuse, with a check).

Before sending, the server is asked to reuse what it may already hold: new
files that a restore point has unchanged (same place, size and date; e.g.
brought back by Restore my files), and folders that were skipped and aren't
any more. It clones them there (btrfs: instant, no space); rsync then checks
again and sends only what's really different.
"""

import os

from omabackups.backup.changes import Plan
from omabackups.backup.skips import Skips
from omabackups.core import log

NEEDS_GATE = 8


def fresh_files(plan: Plan, snapshot: str, renamed: tuple[str, str] | None = None) -> list:
    """New files the server may hold already. renamed (new, old): this user's
    home had another name on the computer it came from (Migrate): the server
    may hold the file under that name too."""
    out = []
    for rel in plan.fresh:
        try:
            info = os.lstat(os.path.join(snapshot, rel))
        except OSError:
            continue
        if os.path.isfile(os.path.join(snapshot, rel)) and not os.path.islink(os.path.join(snapshot, rel)):
            entry = [rel, info.st_size, info.st_mtime_ns]
            if renamed and rel.startswith(renamed[0] + "/"):
                entry.append(renamed[1] + rel[len(renamed[0]):])
            out.append(entry)
    return out


def unskipped(snapshot: str, old_patterns: list, now: Skips) -> tuple[list, list]:
    """What the old skip list left out and the new one doesn't, top-most only:
    (folders, files as [path, size, date]). Files are checked one by one on
    the server (same place, size and date); a folder is reused whole."""
    old = Skips(old_patterns)
    folders, files = [], []
    for root, dirs, names in os.walk(snapshot):
        rel_root = os.path.relpath(root, snapshot)
        for name in list(dirs) + names:
            rel = name if rel_root == "." else f"{rel_root}/{name}"
            if not old.skipped(rel) or now.skipped(rel):
                continue
            if name in dirs:
                folders.append(rel)
                dirs.remove(name)          # its contents come with it
            else:
                try:
                    info = os.lstat(os.path.join(root, name))
                except OSError:
                    continue
                if os.path.isfile(os.path.join(root, name)) and not os.path.islink(os.path.join(root, name)):
                    files.append([rel, info.st_size, info.st_mtime_ns])
        # Below a folder neither list skips, nothing can have been skipped: stop looking.
        dirs[:] = [d for d in dirs if _may_hold_skips(old, f"{rel_root}/{d}".lstrip("./"))]
    return folders, files


def _may_hold_skips(old: Skips, rel: str) -> bool:
    """Could anything under rel have been skipped by the old list? (any-depth
    rules can match anywhere; exact paths only under their own folders)"""
    for p in old.patterns:
        body = p.lstrip("!")
        if not body.startswith("/") or body.lstrip("/").startswith(rel.rstrip("/") + "/"):
            return True
    return False


def ask(gate, bid: str, line: str, part: str, dirs: list, files: list) -> dict:
    if not dirs and not files:
        return {"dirs": 0, "files": 0, "bytes": 0}
    import json
    answer = gate.call("reuse", bid, line, part, data=json.dumps({"dirs": dirs, "files": files}).encode())
    log.get("reuse").info("%s: reused %s folders, %s files (%s bytes not sent)",
                          part, answer["dirs"], answer["files"], answer["bytes"])
    return answer
