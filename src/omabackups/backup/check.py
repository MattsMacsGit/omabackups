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
    for rel in plan.files:
        try:
            info = os.lstat(os.path.join(snapshot, rel))
        except OSError:
            continue
        if not os.path.isdir(os.path.join(snapshot, rel)):
            total += info.st_size
    return total


def folder_size(path: str) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.lstat(os.path.join(root, name)).st_size
            except OSError:
                pass
    return total


def away_limit(away: bool, anyway: bool, size: int | None, limit_mb: int) -> None:
    if away and not anyway and (size is None or size > limit_mb * 1_000_000):
        raise AwayWait(size, limit_mb)


def make_room(gate, bid: str, needed: int, logger) -> list[str]:
    """Make sure `needed` bytes fit; thin the oldest restore points if not."""
    gone = []
    while True:
        space = gate.call("space", bid)
        free = space.get("free")
        if free is None or needed <= free * ROOM:
            return gone
        info = gate.call("points", bid)
        kept = set(info["kept"].get("kept", [])) | {info["kept"].get("return_point")}
        candidates = thinning.space_order(info["points"], kept)
        if not candidates:
            raise OmaError(
                f"Your backup is full: this backup needs {human(needed)} and there's "
                f"{human(free)} left, even after removing old restore points.",
                "Make your backup bigger, or skip big folders you don't need backed up.",
                f"box {human(space.get('box', 0))}, used {human(space.get('used', 0))}",
                code="backup-full")
        logger.info("making room: removing %s", candidates[0])
        gate.call("delete", bid, candidates[0])
        gone.append(candidates[0])
        time.sleep(2)   # btrfs frees space a moment after a delete
