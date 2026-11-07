"""What's inside a backup box (BUILD 5.4): the same on a server and a disk.

backup.json   format version, backup ID, created
owner.json    the owner system now + the handover history (D22)
lines.json    the backup lines (D22a)
kept.json     kept restore points and the Return point
current/<line>/   the working copy of each line in use
points/<line>-<date>-<time>/   one restore point
"""

import json
import time
from pathlib import Path

import conf

FORMAT = 1
FIRST_LINE = "001"


def _write(path: Path, data: dict) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _read(path: Path, default: dict) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def make(inside: Path, bid: str, owner_system: str, host) -> None:
    now = int(time.time())
    (inside / "current").mkdir()
    (inside / "points").mkdir()
    host.make_subvolume(inside / "current" / FIRST_LINE)
    _write(inside / "owner.json", {"owner": owner_system, "since": now, "history": []})
    _write(inside / "lines.json", {"lines": [
        {"line": FIRST_LINE, "owner": owner_system, "from": None, "read_only": False, "started": now}]})
    _write(inside / "kept.json", {"kept": [], "return_point": None})
    # Last: a box with backup.json is a finished box.
    _write(inside / "backup.json", {"format": FORMAT, "id": bid, "created": now})


def check(inside: Path, bid: str) -> None:
    info = _read(inside / "backup.json", {})
    if info.get("id") != bid or info.get("format") != FORMAT:
        from registry import Refused
        raise Refused("this box doesn't hold the backup it should (or is from another version)")


def points(inside: Path) -> list[str]:
    try:
        return sorted(p.name for p in (inside / "points").iterdir() if conf.POINT.match(p.name))
    except FileNotFoundError:
        return []


def kept(inside: Path) -> dict:
    return _read(inside / "kept.json", {"kept": [], "return_point": None})


def write_kept(inside: Path, kept: dict) -> None:
    _write(inside / "kept.json", kept)


def owner(inside: Path) -> dict:
    return _read(inside / "owner.json", {})


def lines(inside: Path) -> list[dict]:
    return _read(inside / "lines.json", {"lines": []})["lines"]


def newest_in_line(names: list[str], line: str) -> str | None:
    mine = [n for n in names if n.startswith(f"{line}-")]
    return max(mine) if mine else None
