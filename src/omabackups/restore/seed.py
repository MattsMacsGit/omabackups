"""After a rescue, the first backup is quick, not a full check (stage 10):
the rescue gives the restored disk the backup's "since" snapshots, as a
backup would have left them.

Only when the point rescued from is the NEWEST of its line on the server: a
backup lays "what changed since the snapshot" onto that line's newest point,
so the two must start out the same. From an older point (going back before a
bad update), nothing is seeded and the first backup checks every file: slow,
always right. Quick Rescue seeds the system only (the home folders come back
later with Restore my files, and get checked).

The record (backup.json) is the one restored with the system: it describes
the backup before this point, so it's brought up to this point here. Its
skip-list fingerprints stay: if the skip list changed meanwhile, the first
backup sees that and checks every file (the safe way).
"""

import json
import subprocess
import time
from pathlib import Path

from omabackups.backup.source import SNAPSHOTS

RECORD = "var/lib/omabackups/backup.json"


def newest_of_line(point: str, points: list[str]) -> bool:
    line = point.split("-", 1)[0]
    mine = sorted(p for p in points if p.startswith(f"{line}-"))
    return bool(mine) and mine[-1] == point


def seed(top: Path, point: str, full: bool) -> dict:
    """`top`: the new btrfs's top level (with @ and @home). Returns what was
    made {part: snapshot name}; the restored record is pointed at them."""
    stamp = time.strftime("%Y%m%dT%H%M%S") + "-rescue"
    snaps = top / SNAPSHOTS
    if not snaps.exists():
        subprocess.run(["btrfs", "subvolume", "create", str(snaps)], check=True, capture_output=True)
    made = {}
    for part, sub in (("system", "@"), ("home", "@home")) if full else (("system", "@"),):
        name = f"{part}-{stamp}"
        subprocess.run(["btrfs", "subvolume", "snapshot", "-r", str(top / sub), str(snaps / name)],
                       check=True, capture_output=True)
        made[part] = name
    point_record(top / "@" / RECORD, point, made)
    return made


def point_record(path: Path, point: str, made: dict) -> None:
    """The restored record, brought up to the rescued point: these snapshots
    are the "since" point, the backup finished there."""
    try:
        record = json.loads(path.read_text())
    except (OSError, ValueError):
        record = {}
    since = {k: v for k, v in (record.get("since") or {}).items() if k in made}
    since.update(made)
    record.update({"since": since, "finished": True, "last_point": point,
                   "seeded_by_rescue": point})
    if "home" not in made:
        (record.get("skips") or {}).pop("home", None)     # home: checked file by file
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2) + "\n")
