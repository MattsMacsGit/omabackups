"""Everything the panel shows, in one answer (BUILD 6.1 D, 7.1).

Read only from files every user can read: the backup record, the location,
the progress file, the health verdict, and this user's settings and state.
Lines appear only when true, each with its colour (BUILD 7.0): red only for a
real problem's title, yellow for a warning, blue for something waiting.
"""

import json
import re
import time
from datetime import datetime

from omabackups import __version__
from omabackups.backup import health as backup_health
from omabackups.backup import progress
from omabackups.core import config, flow, ids, paths, state

POINT = re.compile(r"^(\d{3})-(\d{4})-(\d{2})-(\d{2})-(\d{2})(\d{2})$")


def _read(path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def point_time(name: str) -> int | None:
    m = POINT.match(name)
    if not m:
        return None
    _, y, mo, d, h, mi = (int(x) for x in m.groups())
    return int(datetime(y, mo, d, h, mi).timestamp())


def points(record: dict) -> list[dict]:
    """The restore points, newest first, with which are kept: this computer's
    and, after a Migrate, the old computer's line with the Return point."""
    kept = set(record.get("kept") or [])
    names = set(record.get("point_skips") or ([record["last_point"]] if record.get("last_point") else []))
    names |= set(record.get("all_points") or [])        # every line: the old computer's too
    return [{"name": n, "when": point_time(n), "kept": n in kept, "line": n[:3],
             "return_point": n == record.get("return_point")} for n in sorted(names, reverse=True)]


def header(server: dict, record: dict, pts: list) -> dict | None:
    if not server:
        return None
    disk = server.get("kind") == "disk"
    return {"where": f"your backup disk ({server.get('model') or 'plugged in here'})" if disk
            else "your backup server", "kind": server.get("kind", "server"),
            "address": server.get("address"), "model": server.get("model"),
            "last_point": record.get("last_point"), "last_finished": record.get("last_finished"),
            "not_included": record.get("not_included", []), "size": server.get("size"),
            "space": record.get("space") or {}, "points_count": len(pts),
            "oldest": pts[-1]["name"] if pts else None, "cipher": server.get("cipher")}


def line(kind: str, colour: str, title: str, text: str = "", action: str = "", **more) -> dict:
    return {"kind": kind, "colour": colour, "title": title, "text": text, "action": action, **more}


def lines(step, settings: dict, record: dict, now: dict, mine: dict) -> list[dict]:
    out = []
    everyday = step is flow.Step.EVERYDAY
    if now.get("waiting") == "away":
        out.append(line("waiting-network", "blue", "Waiting for a known network",
                        now.get("error", {}).get("what", ""), "away", size=now.get("size"),
                        limit_mb=now.get("limit_mb")))
    elif not now.get("running") and now.get("ok") is False and now.get("error"):
        error = now["error"]
        if error.get("code") == "backup-full":       # D50
            out.append(line("full", "red", "This won't fit on your backup location",
                            f"{error.get('what', '')} {error.get('todo', '')}".strip(), "pick",
                            details=error.get("details", "")))
        elif error.get("code") == "unreachable":
            out.append(line("unreachable", "yellow", "Your backup can't be reached",
                            error.get("todo", ""), details=error.get("details", "")))
        else:
            out.append(line("failed", "red", "The last backup didn't finish",
                            f"{error.get('what', '')} {error.get('todo', '')}".strip(),
                            details=error.get("details", "")))
    if everyday and (record.get("automatic_paused") or not settings["automatic.on"]):
        out.append(line("automatic-off", "blue", "Automatic backups wait until you press Back up now",
                        "They start again by themselves once that backup is done."))
    verdict = backup_health.load()
    if verdict.get("state") == "damaged":
        out.append(line("health", "red", "Your backup's health check found damaged files",
                        "They're sent again at the next backup, which checks every file's contents."))
    elif verdict.get("state") == "warning":
        out.append(line("health", "yellow", "Your backup's disk reported read or write errors",
                        "Check its cable and power; it may be tiring."))
    if record.get("not_included"):
        out.append(line("not-included", "yellow", "Some folders aren't backed up",
                        "Each is a separate btrfs subvolume, which a snapshot can't include: "
                        + ", ".join(record["not_included"])))
    if everyday and not mine.get("rescue_usb"):
        out.append(line("no-rescue-usb", "yellow", "No Rescue USB yet",
                        "A USB stick that brings this computer back if it won't start. "
                        "Click to make one.", "rescue"))
    return out


def _browsing() -> dict | None:
    from omabackups.restore import browse
    return browse.still_open(browse.current())


def _migrate() -> dict | None:
    """Migrate's own state (6.1 F); once Restore my files has finished for its
    restore point, that step is done (written here, on the user's side)."""
    mine = state.read(flow.MIGRATE)
    if not mine:
        return None
    restored = _read(paths.system_run_dir() / "restore.json")
    if not mine.get("files_restored") and restored.get("done") and restored.get("point") == mine.get("point"):
        mine = {**mine, "files_restored": True}
        state.write(flow.MIGRATE, mine)
    if not mine.get("files_restored") and mine.get("files"):
        from pathlib import Path
        from omabackups.restore.files import already_here
        mine = {**mine, "files_here": already_here(Path.home(), mine["files"])}
    if mine.get("restart"):
        try:
            booted = time.time() - float(open("/proc/uptime").read().split()[0])
        except (OSError, ValueError):
            booted = time.time()
        mine = {**mine, "restart_needed": booted < mine.get("at", 0)}
    return mine


def build() -> dict:
    step = flow.where()
    system = ids.system_id()
    server = _read(paths.server_file())
    record = _read(paths.system_state_dir() / "backup.json")
    now = progress.read()
    if now.get("running") and not progress.alive(now):
        now = {**now, "running": False}
    try:
        settings = config.load()
    except Exception:  # noqa: BLE001 - a bad settings file shows as defaults here; settings says why
        settings = config.defaults()
    mine = state.read("panel") or {}
    migrate = _migrate()
    step = flow.where()                 # again: finishing Migrate can move it on
    pts = points(record)
    return {
        "flow": step.value, "system": {"id": system, "short": ids.short(system)},
        "version": __version__, "header": header(server, record, pts), "points": pts,
        "kept": record.get("kept") or [], "return_point": record.get("return_point"),
        "settings": settings, "first_backup_done": bool(record.get("last_point")),
        "running": now if now.get("running") else None,
        # D49: a backup that started sending and didn't finish: "Resume backup".
        "unfinished": record.get("finished") is False and not now.get("running"),
        "lines": lines(step, settings, record, now, mine),
        "rescue_usb": mine.get("rescue_usb"), "rescue_later": bool(mine.get("rescue_later")),
        "browsing": _browsing(),      # D37
        "migrate": migrate,
        "restoring": _read(paths.system_run_dir() / "restore.json") or None,
    }
