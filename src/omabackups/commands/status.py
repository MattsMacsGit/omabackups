"""`omabackups status`: everything the panel shows, in one answer."""

import json
from datetime import datetime

from omabackups import __version__
from omabackups.backup import progress
from omabackups.core import flow, ids, paths
from omabackups.core.events import Events

_TEXT = {
    flow.Step.NOT_SET_UP: (
        "OmaBackups is not set up on this computer yet.\n"
        "Open the OmaBackups panel and choose Set up backups, "
        "or Migrate from another system."
    ),
    flow.Step.SETTING_UP: "OmaBackups is being set up: the first backup hasn't run yet.",
    flow.Step.MIGRATING: "Migrate from another system has started and isn't finished yet.",
    flow.Step.RESTORE_FILES: "Restore my files to finish. Automatic backups wait until then.",
    flow.Step.EVERYDAY: "OmaBackups is set up and backing up.",
}


def add(sub) -> None:
    p = sub.add_parser("status", help="where OmaBackups is up to on this computer")
    p.set_defaults(run=run)


def run(args, events: Events) -> int:
    step = flow.where()
    system = ids.system_id()
    data = {
        "flow": step.value,
        "system": {"id": system, "short": ids.short(system)},
        "version": __version__,
        # Filled in by later stages: the panel header and the lines that
        # appear only when true (BUILD 6.1 D).
        "header": _header(),
        "lines": [],
    }
    text = _TEXT[step]
    if data["header"] and data["header"].get("last_point"):
        h = data["header"]
        when = datetime.fromtimestamp(h["last_finished"]).strftime("%A %-I:%M %p").replace(" 0", " ")
        text += f"\nLast backup: {when} (restore point {h['last_point']}), to {h['where']}."
    progress_now = progress.read()
    if progress_now.get("running"):
        text += f"\nRunning now: {progress.text(progress_now)}"
    elif progress_now.get("waiting") == "away":
        # A line that appears only when true (BUILD 6.1 D, D17).
        data["lines"].append({"kind": "waiting-network", "size": progress_now.get("size"),
                              "limit_mb": progress_now.get("limit_mb")})
        text += ("\nWaiting for a known network: " + progress_now["error"]["what"]
                 + "\n" + progress_now["error"]["todo"])
    events.result({**data, "running": progress_now if progress_now.get("running") else None}, text)
    return 0


def _header() -> dict | None:
    """Last backup and where it went (BUILD 6.1 D). Both files are readable by everyone."""
    try:
        server = json.loads(paths.server_file().read_text())
    except (OSError, ValueError):
        return None
    try:
        record = json.loads((paths.system_state_dir() / "backup.json").read_text())
    except (OSError, ValueError):
        record = {}
    return {"where": "your backup server", "address": server.get("address"),
            "last_point": record.get("last_point"), "last_finished": record.get("last_finished"),
            "size": server.get("size")}
