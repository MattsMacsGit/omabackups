"""Smart thinning (D18, as 1.x): every restore point from the last 24 hours,
then the newest of each day for 30 days, then the newest of each week.
Per backup line. Never the newest of a line, never a kept one or the Return
point (and the gatekeeper refuses those too)."""

import re
from datetime import datetime, timedelta

KEEP_ALL_FOR = timedelta(hours=24)
DAILY_FOR = timedelta(days=30)
NAME = re.compile(r"^(\d{3})-(\d{4})-(\d{2})-(\d{2})-(\d{2})(\d{2})$")


def when(name: str) -> datetime | None:
    m = NAME.match(name)
    if not m:
        return None
    _, y, mo, d, h, mi = m.groups()
    return datetime(int(y), int(mo), int(d), int(h), int(mi))   # local time, as named


def to_delete(names: list[str], now: datetime, kept: set[str] = frozenset()) -> list[str]:
    """The restore points thinning removes, oldest first."""
    out = []
    for line in sorted({n[:3] for n in names if NAME.match(n)}):
        mine = sorted((n for n in names if n.startswith(f"{line}-") and NAME.match(n)), reverse=True)
        seen = set()
        for i, name in enumerate(mine):
            age = now - when(name)
            if i == 0 or age <= KEEP_ALL_FOR or name in kept:
                continue
            stamp = when(name)
            bucket = ("day", stamp.date()) if age <= DAILY_FOR else ("week", *stamp.isocalendar()[:2])
            if bucket in seen:
                out.append(name)
            else:
                seen.add(bucket)
    return sorted(out)


def space_order(names: list[str], kept: set[str] = frozenset()) -> list[str]:
    """What may go when the backup is full, oldest first: never a line's newest,
    never a kept one (1.x: one at a time, checking real free space after each)."""
    newest = {}
    for name in names:
        if NAME.match(name) and name > newest.get(name[:3], ""):
            newest[name[:3]] = name
    return sorted(n for n in names
                  if NAME.match(n) and n not in kept and n not in newest.values())
