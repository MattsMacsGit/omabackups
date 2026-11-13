"""After the restore point is made: thinning, and what the record keeps
about the restore points (their skip lists, the newest one)."""

import time
from datetime import datetime

from omabackups.backup import skips, thinning
from omabackups.core.errors import OmaError
from omabackups.where.server import Gate

KEPT = {}     # the kept restore points, as thinning last saw them


def thin(gate: Gate, bid: str, logger, smart: bool = True) -> tuple[list[str], list[str] | None]:
    """Smart thinning after each backup (D18); switched off (D35), every
    restore point stays until the backup needs the room. A problem here never
    fails the backup. Returns (the restore points removed, the ones left; None
    if unknown)."""
    gone, left = [], None
    try:
        info = gate.call("points", bid)
        kept = set(info["kept"].get("kept", [])) | {info["kept"].get("return_point")}
        for old in thinning.to_delete(info["points"], datetime.now(), kept) if smart else []:
            gate.call("delete", bid, old)
            gone.append(old)
        left = [n for n in info["points"] if n not in gone]
        KEPT.clear()
        KEPT.update(info["kept"])
    except OmaError as exc:
        logger.warning("thinning: %s | %s", exc.what, exc.details)
    return gone, left


def point_skips(record: dict, name: str, made: dict, left: list[str] | None) -> dict:
    """Each restore point with the skip list it was made with, for the picker's
    colours (what the backup holds); points thinning removed drop out."""
    out = dict(record.get("point_skips") or {})
    out[name] = {"time": int(time.time()), "skips": made}
    if left is not None:
        out = {n: v for n, v in out.items() if n in set(left) | {name}}
    return out


def changes_latest(gate: Gate, bid: str, line: str) -> str | None:
    names = [n for n in gate.call("points", bid)["points"] if n.startswith(f"{line}-")]
    return max(names) if names else None


def finished_record(job, name: str, thinned: list, left: list | None, space: dict,
                    manual: bool) -> dict:
    """The backup's record once it finished: what the next backup, the
    panel and the picker read."""
    record, patterns = job.record, {p: skips.for_part(p).patterns for p in job.fingerprints}
    return {"finished": True, "since": job.since, "skips": job.fingerprints, "last_point": name,
            "skip_patterns": patterns,
            "point_skips": point_skips(record, name, patterns, left),
            "last_finished": int(time.time()), "how": job.how, "thinned": thinned,
            "away": job.away, "not_included": job.left_out, "manifests": job.manifests,
            "sent": job.sender.stats,
            # D29: a manual backup ends the wait; an automatic one leaves it as it was.
            "automatic_paused": False if manual else record.get("automatic_paused", False),
            "kept": KEPT.get("kept", record.get("kept", [])),
            "return_point": KEPT.get("return_point", record.get("return_point")),
            "space": {k: space.get(k) for k in ("box", "used", "free")},
            # Every restore point in the backup, every line: after a Migrate the
            # old computer's (and the Return point) stay listed (stage 8 lesson).
            "all_points": left if left is not None else record.get("all_points", []),
            "resent_for_pass": job.verdict.get("pass_started") if job.resend
            else record.get("resent_for_pass")}
