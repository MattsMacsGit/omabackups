"""Check first (BUILD 5.1): how big, will it fit, the away limit (D17).

Runs after the change lists are made and before anything is sent, so a
backup that can't or shouldn't go ahead stops with nothing half done.
"""

import os
import time

from omabackups.backup import thinning
from omabackups.backup.changes import Plan
from omabackups.core.errors import OmaError

ROOM = 0.95        # never fill the box past this


class AwayWait(OmaError):
    """Away from home, and bigger than the limit: waits for your answer (D17)."""

    def __init__(self, size: int | None, limit_mb: int):
        shown = f"{human(size)}" if size is not None else "a full check (its size isn't known yet)"
        super().__init__(
            f"This backup is {shown}, bigger than your {limit_mb} MB limit away from home.",
            "Back up now anyway: omabackups away answer now. Or let it wait until "
            "you're on a known network: omabackups away answer wait.",
            code="away-wait")
        self.size, self.limit_mb = size, limit_mb


def human(size: int) -> str:
    for unit in ("bytes", "KB", "MB", "GB", "TB"):
        if size < 1000 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "bytes" else f"{size:.1f} {unit}"
        size /= 1000
    return ""


def size_of(plan: Plan, snapshot: str) -> int:
    """About how much the everyday mix will send."""
    total = sum(n for spans in plan.ranges.values() for _, n in spans)
    light = set(plan.light)            # only details changed: a few bytes, not the file
    for rel in plan.files:
        if rel in light:
            continue
        try:
            info = os.lstat(os.path.join(snapshot, rel))
        except OSError:
            continue
        if not os.path.isdir(os.path.join(snapshot, rel)):
            total += info.st_size
    return total


def folder_changes(path: str, before: dict) -> tuple[int, dict]:
    """For a part copied as it is (/boot): about how much rsync will send,
    from the list of its files (size, date) kept after the last backup."""
    total, now = 0, {}
    for root, _dirs, files in os.walk(path):
        for name in files:
            full = os.path.join(root, name)
            try:
                info = os.lstat(full)
            except OSError:
                continue
            rel = os.path.relpath(full, path)
            now[rel] = [info.st_size, info.st_mtime_ns]
            if before.get(rel) != now[rel]:
                total += info.st_size
    return total, now


def away_limit(away: bool, anyway: bool, size: int | None, limit_mb: int) -> None:
    if away and not anyway and (size is None or size > limit_mb * 1_000_000):
        raise AwayWait(size, limit_mb)


WONT_FIT_TODO = ("Remove some files from what gets backed up (Choose what gets backed up), "
                 "or pick a new disk for your backup (set up backups again).")


def wont_fit(needed: int | None, free: int | None, space: dict) -> OmaError:
    """D50: said before anything is sent, in plain words, with the numbers."""
    numbers = (f": it needs {human(needed)} and there's {human(free)} free"
               if needed is not None and free is not None else "")
    return OmaError(f"This won't fit on your backup location{numbers}.", WONT_FIT_TODO,
                    f"box {human(space.get('box', 0))}, used {human(space.get('used', 0))}, "
                    f"free {human(space.get('free', 0))}", code="backup-full")


def make_room(gate, bid: str, needed: int, logger, may_delete: bool = True) -> list[str]:
    """Make sure `needed` bytes fit; thin the oldest restore points if not.
    With smart thinning off (`may_delete` False, D35) nothing is ever deleted
    by itself: the backup stops and says what to do."""
    gone = []
    while True:
        space = gate.call("space", bid)
        free = space.get("free")
        if free is None or needed <= free * ROOM:
            return gone
        if not may_delete:
            raise OmaError(
                f"Your backup is full: this backup needs {human(needed)} and there's "
                f"{human(free)} left. Smart thinning is off, so no restore points were deleted.",
                "Turn on Smart thinning (Settings › Restore points), or make room by deleting "
                "restore points you don't need: omabackups points lists them, and "
                "omabackups delete <restore point> deletes one.",
                f"box {human(space.get('box', 0))}, used {human(space.get('used', 0))}",
                code="backup-full")
        info = gate.call("points", bid)
        kept = set(info["kept"].get("kept", [])) | {info["kept"].get("return_point")}
        candidates = thinning.space_order(info["points"], kept)
        if not candidates:
            raise wont_fit(needed, free, space)
        logger.info("making room: removing %s", candidates[0])
        gate.call("delete", bid, candidates[0])
        gone.append(candidates[0])
        time.sleep(2)   # btrfs frees space a moment after a delete
