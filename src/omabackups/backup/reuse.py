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


def fresh_files(plan: Plan, snapshot: str) -> list:
    out = []
    for rel in plan.fresh:
        try:
            info = os.lstat(os.path.join(snapshot, rel))
        except OSError:
            continue
        if os.path.isfile(os.path.join(snapshot, rel)) and not os.path.islink(os.path.join(snapshot, rel)):
            out.append([rel, info.st_size, info.st_mtime_ns])
    return out


def unskipped(snapshot: str, old_patterns: list, now: Skips) -> list:
    """Top-most paths that the old skip list left out and the new one doesn't."""
    gone = Skips([p for p in old_patterns if p not in now.patterns])
    if not gone.patterns:
        return []
    found = []
    for root, dirs, files in os.walk(snapshot):
        rel_root = os.path.relpath(root, snapshot)
        for name in list(dirs) + files:
            rel = name if rel_root == "." else f"{rel_root}/{name}"
            if gone.skipped(rel) and not now.skipped(rel):
                found.append(rel)
                if name in dirs:
                    dirs.remove(name)      # its contents come with it
    return found


def ask(gate, bid: str, line: str, part: str, dirs: list, files: list) -> dict:
    if not dirs and not files:
        return {"dirs": 0, "files": 0, "bytes": 0}
    import json
    answer = gate.call("reuse", bid, line, part, data=json.dumps({"dirs": dirs, "files": files}).encode())
    log.get("reuse").info("%s: reused %s folders, %s files (%s bytes not sent)",
                          part, answer["dirs"], answer["files"], answer["bytes"])
    return answer
