"""Damaged files, sent again by name (audit 4.2; 1.x health.py resend-list,
backup.sh resend_damaged).

A backup can't notice a damaged file by itself (its size and date still
match), so it asks the health check's list and sends each one this computer
still has, whole, once. resent.json is what's been dealt with: every damaged
name the check gave (one per restore point sharing the bad block), which
were sent again, which weren't here to send, and when damage was found, so
repeated damage can say the disk may be failing (SPEC §10).
"""

import json
import time
from pathlib import Path

from omabackups.core import paths
from omabackups.core.state import write_atomic

REPEAT = 90 * 86400        # damage more than once in three months: the disk may be failing


def record_file() -> Path:
    return paths.system_state_dir() / "health-resent.json"


def load() -> dict:
    try:
        return json.loads(record_file().read_text())
    except (OSError, ValueError):
        return {}


def save(record: dict) -> None:
    write_atomic(record_file(), (json.dumps(record, indent=1) + "\n").encode(), 0o644)


def damaged_in(names: list, part: str) -> dict:
    """{path inside the part: [every name the check gave it]}. Named from
    the box's top: points/<point>/<part>/<path> or current/<line>/<part>/<path>."""
    out = {}
    for name in names or []:
        bits = str(name).split("/")
        if len(bits) < 4 or bits[0] not in ("points", "current") or bits[2] != part or ".." in bits:
            continue
        out.setdefault("/".join(bits[3:]), []).append(str(name))
    return out


def resend(job) -> dict:
    """Before the restore point is made: each damaged file this computer still
    has goes again, whole; the ones it no longer has are noted."""
    names = job.verdict.get("paths") or []
    if not names:
        return {}
    record = load()
    handled = set(record.get("handled") or [])
    new_damage = [n for n in names if n not in handled and n not in set(record.get("seen") or [])]
    if new_damage:            # every time damage is found, it counts
        record["found"] = (record.get("found") or []) + [int(time.time())]
        record["seen"] = sorted(set(record.get("seen") or []) | set(new_damage))
    sent_all, missing_all = [], []
    for part, _skip, new, _plan in job.work:
        if new is None:
            continue
        waiting = {rel: ns for rel, ns in damaged_in(names, part.name).items() if any(n not in handled for n in ns)}
        sent = [rel for rel in waiting if (Path(str(new)) / rel).is_file() and not (Path(str(new)) / rel).is_symlink()]
        missing = [rel for rel in waiting if rel not in sent]
        if sent:
            job.progress("damaged", part.name)
            job.sender.resend(part.name, str(new), sent)
        for rel in waiting:
            handled.update(waiting[rel])
        sent_all += [f"{part.name}/{r}" for r in sent]
        missing_all += [f"{part.name}/{r}" for r in missing]
        if sent or missing:
            job.logger.info("damaged %s: %d sent again, %d no longer on this computer",
                            part.name, len(sent), len(missing))
    record.update(handled=sorted(handled), sent=sorted(set(record.get("sent") or []) | set(sent_all)),
                  missing=sorted(set(record.get("missing") or []) | set(missing_all)), at=int(time.time()))
    save(record)
    return {"sent": sent_all, "missing": missing_all}


def failing(record: dict | None = None, now: float | None = None) -> bool:
    """Damage found more than once in three months: the disk may be failing."""
    record = load() if record is None else record
    now = time.time() if now is None else now
    return len([t for t in record.get("found") or [] if now - t < REPEAT]) > 1
