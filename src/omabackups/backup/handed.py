"""D22a: the old computer after a Migrate. Its backup line is read-only once
the new computer has taken the backup over; it can still bring files back,
but never backs up into it. A backup on it stops before anything is sent and
says so plainly; Set up a new backup gives it a line of its own (root/
job_newline.py). Without this, the server just refused: "a reader key can't
do that" (demo film, 15 Nov 2026)."""

from datetime import datetime

from omabackups.core.errors import OmaError

TITLE = "This computer's backup was handed over"
OFFER = ("A backup line of its own on the same server, starting from this computer's "
         "last restore point: nothing is sent again.")


def check(gate, bid: str, line: str) -> None:
    """Raises "handed-over" when this computer's line is read-only."""
    info = gate.call("points", bid)
    mine = next((e for e in info.get("lines") or [] if e.get("line") == line), None)
    if not mine or not mine.get("read_only"):
        return
    owner = info.get("owner") or {}
    raise OmaError(said(gate, bid, info), f"Set up a new backup on the panel (or: omabackups new-line). {OFFER}",
                   f"line {line} is read-only; the backup's owner is {owner.get('owner', 'unknown')}",
                   code="handed-over")


def said(gate, bid: str, info: dict) -> str:
    owner = info.get("owner") or {}
    who = _computer(gate, bid, info, owner.get("owner", "")) or "Another computer"
    since = owner.get("since")
    when = f" on {datetime.fromtimestamp(since).strftime('%a %-d %b')}" if isinstance(since, (int, float)) else ""
    return (f"{who} took this backup over (Migrate){when}. This computer can still bring files back, "
            "but no longer backs up into it.")


def _computer(gate, bid: str, info: dict, system: str) -> str:
    """The new owner's name: from its line's newest restore point."""
    lines = [e["line"] for e in info.get("lines") or [] if e.get("owner") == system and not e.get("read_only")]
    points = sorted(p for p in info.get("points") or [] if any(p.startswith(f"{n}-") for n in lines))
    if not points:
        return ""
    try:
        return ((gate.call("info", bid, points[-1]) or {}).get("point") or {}).get("computer", "")
    except OmaError:
        return ""
