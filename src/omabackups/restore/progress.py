"""Restore my files' progress, the backup's own way round (D63).

The backup's meter (backup/meter.py) and the same reading of rsync's
--info=progress2 bytes: percent of a known total, amount, speed, time left.
The total comes from the sizes the server measures for each restore point,
or from Choose what comes back's own "Bringing back X". Before rsync has
listed the files there is nothing to count: step "list" says so.
"""

import time

from omabackups.backup.meter import Meter
from omabackups.backup.send import _PROGRESS

EVERY = 1.0          # write the state at most once a second


def planned(sizes: dict | None, user_dir: str, only: list[str] | None, leave_out: list[str] | None,
            given: int | None = None) -> int:
    """Bytes coming back: Choose what comes back's own total when it gave
    one; else from the restore point's measured sizes (the home part:
    {"": [bytes, files], "<user>": [...], "<user>/Documents": [...]}).
    0 when it can't be known (an older server): the bar sweeps."""
    if isinstance(given, int) and given > 0:
        return given
    home = (sizes or {}).get("home") or {}

    def size(rel: str) -> int:
        entry = home.get(rel)
        return int(entry[0]) if isinstance(entry, list) and entry else 0
    if only is not None:
        return sum(size(f"{user_dir}/{p.strip('/')}") for p in only)
    if leave_out:
        return 0                     # the chooser sends its own total
    return size(user_dir)


class Watch:
    """Feeds rsync's output to the meter and says how it's going."""

    def __init__(self, state: dict, total: int, say, clock=time.monotonic):
        self.state, self.say, self.clock = state, say, clock
        self.meter = Meter(total, clock=clock)
        self.window = b""
        self.last = 0.0
        state.update(step="list", percent=0, sent=0, total=total)

    def feed(self, chunk: bytes) -> None:
        self.window = (self.window + chunk)[-600:]
        found = _PROGRESS.findall(self.window)
        if not found:
            return
        self.meter.update(sent=int(found[-1].replace(b",", b"")))
        now = self.clock()
        if self.state.get("step") != "bring" or now - self.last >= EVERY:
            self.last = now
            snap = self.meter.snapshot()
            self.state.update(step="bring", percent=snap["percent"], sent=snap["sent"],
                              total=snap["total"], speed=snap["speed"], left=snap["left"])
            self.say(self.state)
