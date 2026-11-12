"""A full backup's part in a backup run (D49 C): checked once, or carried on.

prepare() runs in the check step, before anything is sent:
- an unfinished full backup with a to-do list that fits (same backup, line,
  skip list, its snapshot still here): btrfs says what changed since that
  snapshot, and the list carries on. No check over the network.
- otherwise: one dry run against the backup server makes the list.
The list is saved with the new snapshot; the copy step sends exactly it.
"""

import re
from dataclasses import dataclass, field

from omabackups.backup import changes, todo
from omabackups.core.errors import OmaError

NEEDS_GATE = 15          # the gatekeeper that lets the check list what it would send
_TOTAL = re.compile(rb"^Total file size: ([\d,]+)", re.M)


@dataclass
class FullList:
    items: list                       # (path, size) to send, in order
    ops: list = field(default_factory=list)    # deletes/renames on the server first
    already: int = 0                  # bytes of this part already on the backup
    resumed: bool = False
    old_snapshot: str = ""            # the last list's snapshot, to drop once this is saved


def _meta(bid: str, line: str, part: str, fingerprint: str, snapshot: str, already: int) -> dict:
    return {"backup": bid, "line": line, "part": part, "fingerprint": fingerprint,
            "snapshot": snapshot, "already": already}


def prepare(part: str, skip, new, snaps, sender, record: dict, bid: str, line: str,
            fingerprint: str, logger) -> FullList:
    loaded = todo.load(part)
    meta = loaded[0] if loaded else {}
    old = meta.get("snapshot", "")
    if (loaded and record.get("finished") is False and todo.fits(meta, bid, line, fingerprint)
            and old and snaps.exists(old)):
        try:
            plan = changes.plan(snaps.dump(old, new), new.name, str(new), skip)
        except OmaError as exc:
            logger.warning("%s: the to-do list can't carry on (%s); checking again", part, exc.details)
            plan = None
        if plan is not None:
            left = todo.remaining(part)
            items = todo.carry(left, plan, str(new))
            sent_before = meta.get("bytes", 0) - sum(size for _, size in left)
            already = meta.get("already", 0) + max(0, sent_before)
            todo.save(part, _meta(bid, line, part, fingerprint, new.name, already), items)
            logger.info("%s: carrying on a full backup: %d of %d items left, %d changed since",
                        part, len(left), meta.get("items", 0), len(plan.files) + len(plan.ranges))
            return FullList(items, plan.ops, already, True, old)
    sender.report({})
    items, deletes, total = sender.check(part, str(new), skip)
    already = max(0, total - sum(size for _, size in items))
    todo.save(part, _meta(bid, line, part, fingerprint, new.name, already), items)
    logger.info("%s: checked once: %d items to send, %d to delete", part, len(items), len(deletes))
    return FullList(items, [["delete", d] for d in deletes], already, False, old)


def total_size(out: bytes) -> int:
    """The part's whole size, from the dry run's stats."""
    m = _TOTAL.search(out)
    return int(m.group(1).replace(b",", b"")) if m else 0


def keep(part: str) -> str:
    """The snapshot an unfinished to-do list needs (never dropped after a failure)."""
    loaded = todo.load(part)
    return loaded[0].get("snapshot", "") if loaded else ""
