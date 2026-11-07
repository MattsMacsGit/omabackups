"""The nightly health check, from this computer's side (D18).

The check itself runs on the server (the gatekeeper's scrub, a slice a
night). This starts tonight's slice at the hour set in Settings, keeps the
latest verdict where status can read it, and tells the next backup when
damaged files must be sent again.
"""

import json
import time
from datetime import datetime

from omabackups.core import log, paths
from omabackups.core.state import write_atomic

PROBLEMS = ("warning", "damaged")


def file():
    return paths.system_state_dir() / "health.json"


def load() -> dict:
    try:
        return json.loads(file().read_text())
    except (OSError, ValueError):
        return {}


def save(verdict: dict) -> None:
    write_atomic(file(), (json.dumps({**verdict, "seen": int(time.time())}, indent=2) + "\n").encode(),
                 0o644)


def due(settings: dict, last_started: int | None, now: datetime | None = None) -> bool:
    now = now or datetime.now()
    if not settings["health.on"] or now.hour != settings["health.at"]:
        return False
    return not last_started or datetime.fromtimestamp(last_started).date() != now.date()


def refresh(gate, bid: str) -> dict:
    """Ask the server for the verdict (gatekeeper 4 or newer) and keep it."""
    if gate.call("version").get("gate", 0) < 4:
        return load()
    verdict = gate.call("health", bid)
    save({**load(), **verdict})
    return verdict


def start_tonight(gate, bid: str, minutes: int, unlock_key: bytes) -> dict:
    logger = log.get("health")
    hold = gate.call("unlock", bid, data=unlock_key)["hold"]
    try:
        verdict = gate.call("health-start", bid, str(minutes))
    finally:
        # Let go: the server keeps the backup open while the check runs, and
        # pauses it when tonight's time is up.
        gate.call("lock", bid, hold)
    save({**load(), **verdict, "started": int(time.time())})
    logger.info("health check started for %s minutes", minutes)
    return verdict


def resend_needed(verdict: dict, record: dict) -> bool:
    """Damage found that no full checksum backup has answered yet."""
    return (verdict.get("state") == "damaged"
            and record.get("resent_for_pass") != verdict.get("pass_started"))
